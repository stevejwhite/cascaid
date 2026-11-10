"""HTTP API for station sessions. Hidden facts are only revealed in the post-station debrief."""

import asyncio
import base64
import json
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import Field

from psychiatry_api.cancellation import until_disconnect
from psychiatry_api.cases import CaseSummary, Expression, load_cases
from psychiatry_api.config import Settings
from psychiatry_api.domain import Contract
from psychiatry_api.feedback.report import Feedback, report
from psychiatry_api.models.errors import ModelError
from psychiatry_api.models.selection import embedding_model, language_model, verify_service
from psychiatry_api.roleplay import sessions
from psychiatry_api.roleplay.classify import (
    CascadeInterpreter,
    TrainedClassifiers,
    classifier_cache,
    student_topics,
)
from psychiatry_api.roleplay.interpret import KeywordInterpreter, ModelInterpreter
from psychiatry_api.roleplay.respond import ModelRolePlayer, TemplateRolePlayer
from psychiatry_api.schemas import ErrorResponse
from psychiatry_api.speech import MAX_BYTES as MAX_AUDIO_BYTES
from psychiatry_api.speech import SpeechError, recognizer, validate_wav, vocabulary_prompt
from psychiatry_api.synthesis import (
    MAX_CHARACTERS,
    SynthesisError,
    spoken_by_character,
    synthesizer,
)


class StartRequest(Contract):
    case_id: str = Field(min_length=1, max_length=60)


class TurnRequest(Contract):
    text: str = Field(min_length=1, max_length=600, pattern=r"\S")
    # Set when the text came from speech recognition (possibly edited before sending).
    transcription_id: str | None = Field(default=None, max_length=32)


class TranscriptionView(Contract):
    transcription_id: str
    text: str
    audio_ms: int
    asr_ms: int


class InterruptionRequest(Contract):
    during: Literal["speaking", "thinking"]
    heard_ms: int = Field(ge=0, le=600_000)


class SpeechRequest(Contract):
    text: str = Field(min_length=1, max_length=MAX_CHARACTERS, pattern=r"\S")
    voice: str = Field(pattern=r"^[a-z]{2}_[a-z]{2,20}$")


class SpeechView(Contract):
    """Audio (base64 WAV) with word and viseme timings in ms from the start of the audio."""

    audio_wav_base64: str
    words: tuple[str, ...]
    word_times_ms: tuple[int, ...]
    word_durations_ms: tuple[int, ...]
    visemes: tuple[str, ...]
    viseme_times_ms: tuple[int, ...]
    viseme_durations_ms: tuple[int, ...]
    voice: str
    model: str
    synthesis_ms: int


class Line(Contract):
    speaker: Literal["candidate", "character"]
    text: str


class Presentation(Contract):
    """How the 3D character currently looks: the affect stage's expression and the fillers it
    may voice while thinking. Says nothing about facts or disclosure."""

    expression: Expression
    hesitations: tuple[str, ...]


class SessionView(Contract):
    session_id: str
    station: CaseSummary
    character_name: str
    phase: Literal["reading", "interview", "ended"]
    created_at: datetime
    interview_deadline: datetime | None
    transcript: tuple[Line, ...]
    presentation: Presentation


class Debrief(Contract):
    session: SessionView
    feedback: Feedback


def presentation(session: sessions.Session) -> Presentation:
    """The affect stage behind the latest reply (the starting stage before any turn)."""
    stages = {stage.id: stage for stage in session.case.affect_stages}
    latest = next((t.affect_stage for t in reversed(session.turns) if t.affect_stage), None)
    stage = stages.get(latest) if latest else next(iter(stages.values()), None)
    if stage is None:
        return Presentation(expression="neutral", hesitations=())
    return Presentation(expression=stage.expression, hesitations=stage.hesitations)


def view(session: sessions.Session) -> SessionView:
    lines = []
    if began := session.first(sessions.Began):
        lines.append(Line(speaker="character", text=began.opening))
    for turn in session.turns:
        lines += [
            Line(speaker="candidate", text=turn.candidate),
            Line(speaker="character", text=turn.reply),
        ]
    return SessionView(
        session_id=session.started.session_id,
        station=CaseSummary.of(session.case),
        character_name=session.case.persona.name,
        phase=session.phase,
        created_at=session.started.at,
        interview_deadline=session.deadline,
        transcript=tuple(lines),
        presentation=presentation(session),
    )


def debrief(session: sessions.Session) -> Debrief:
    return Debrief(session=view(session), feedback=report(session))


def session_router(settings: Settings, generation_slot: asyncio.Lock) -> APIRouter:
    router = APIRouter(prefix="/api/sessions", tags=["Station sessions"])
    store = sessions.SessionStore(settings.sessions_path)
    timeout_ms = int(settings.model_timeout_seconds * 1000)

    classifiers = None

    def components():
        nonlocal classifiers
        if settings.model_backend == "fake":
            return KeywordInterpreter(), TemplateRolePlayer()
        model = language_model(settings)
        interpreter = ModelInterpreter(model, timeout_ms)
        if settings.interpreter == "cascade":
            # Trained once per process, on first use.
            if classifiers is None:
                classifiers = TrainedClassifiers(
                    embedding_model(settings), classifier_cache(settings)
                )
            cases = {case.id: case for case in load_cases(settings.cases_path)}
            interpreter = CascadeInterpreter(
                classifiers, interpreter, cases, student_topics(settings)
            )
        return interpreter, ModelRolePlayer(model, timeout_ms)

    def load(session_id: str) -> sessions.Session:
        try:
            return store.load(session_id)
        except (KeyError, ValueError) as error:
            raise HTTPException(404, "Session not found") from error

    @router.post("", response_model=SessionView, responses={404: {"model": ErrorResponse}})
    def start(body: StartRequest) -> SessionView:
        case = next((c for c in load_cases(settings.cases_path) if c.id == body.case_id), None)
        if case is None:
            raise HTTPException(404, "Station case not found")
        interpreter, role_player = components()
        return view(sessions.create(store, settings, case, interpreter, role_player))

    @router.get("/{session_id}", response_model=SessionView)
    async def read(session_id: str) -> SessionView:
        async with store.lock(session_id):
            return view(sessions.expire(store, load(session_id)))

    @router.post("/{session_id}/begin", response_model=SessionView)
    async def begin(session_id: str) -> SessionView:
        async with store.lock(session_id):
            try:
                return view(sessions.begin(store, load(session_id)))
            except sessions.SessionError as error:
                raise HTTPException(409, str(error)) from error

    @router.post(
        "/{session_id}/turns",
        response_model=SessionView,
        responses={409: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    async def turn(session_id: str, body: TurnRequest, request: Request) -> SessionView:
        async def work() -> SessionView:
            async with store.lock(session_id), generation_slot:
                session = load(session_id)
                if session.started.backend != settings.model_backend:
                    raise HTTPException(409, "The model backend changed; start a new station")
                if settings.model_backend == "local":
                    await verify_service(settings)
                interpreter, role_player = components()
                updated = await sessions.take_turn(
                    store,
                    session,
                    body.text.strip(),
                    interpreter,
                    role_player,
                    body.transcription_id,
                )
                return view(updated)

        try:
            async with asyncio.timeout(2 * settings.model_timeout_seconds + 5):
                return await until_disconnect(request, work())
        except sessions.SessionError as error:
            raise HTTPException(409, str(error)) from error
        except (ModelError, TimeoutError) as error:
            raise HTTPException(
                503, "The simulated character could not reply. Check the local model and retry."
            ) from error

    @router.post(
        "/{session_id}/turns/stream",
        responses={
            200: {
                "description": "Newline-delimited JSON events: {type: pace, slow} (whether the "
                "turn waits for the language model), {type: sentence, text} for each released "
                "sentence, then {type: done, session} or {type: error, status, detail}.",
                "content": {"application/x-ndjson": {}},
            }
        },
    )
    async def turn_stream(session_id: str, body: TurnRequest) -> StreamingResponse:
        """Like POST /turns, but releases the reply sentence by sentence as it is generated."""

        def line(event: dict) -> str:
            return json.dumps(event, ensure_ascii=False) + "\n"

        async def events():
            try:
                async with asyncio.timeout(2 * settings.model_timeout_seconds + 5):
                    async with store.lock(session_id), generation_slot:
                        session = load(session_id)
                        if session.started.backend != settings.model_backend:
                            raise HTTPException(
                                409, "The model backend changed; start a new station"
                            )
                        if settings.model_backend == "local":
                            await verify_service(settings)
                        interpreter, role_player = components()
                        async for kind, payload in sessions.take_turn_stream(
                            store,
                            session,
                            body.text.strip(),
                            interpreter,
                            role_player,
                            body.transcription_id,
                        ):
                            if kind == "pace":
                                yield line({"type": "pace", "slow": payload})
                            elif kind == "sentence":
                                yield line({"type": "sentence", "text": payload})
                            else:
                                done = view(payload).model_dump(mode="json")
                                yield line({"type": "done", "session": done})
            except HTTPException as error:
                yield line({"type": "error", "status": error.status_code, "detail": error.detail})
            except sessions.SessionError as error:
                yield line({"type": "error", "status": 409, "detail": str(error)})
            except (ModelError, TimeoutError):
                yield line(
                    {
                        "type": "error",
                        "status": 503,
                        "detail": "The simulated character could not reply. Check the local model "
                        "and retry.",
                    }
                )

        return StreamingResponse(events(), media_type="application/x-ndjson")

    @router.post(
        "/{session_id}/transcriptions",
        response_model=TranscriptionView,
        responses={
            409: {"model": ErrorResponse},
            413: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}},
            }
        },
    )
    async def transcribe(session_id: str, request: Request) -> TranscriptionView:
        """Transcribe one 16 kHz mono WAV recording. The audio is not stored."""
        if settings.speech_backend == "off":
            raise HTTPException(409, "Speech input is turned off")
        declared = int(request.headers.get("content-length") or 0)
        if declared > MAX_AUDIO_BYTES:
            raise HTTPException(413, "Recordings are limited to 60 seconds")
        data = await request.body()
        try:
            audio = validate_wav(data)
        except SpeechError as error:
            raise HTTPException(413 if error.code == "too_long" else 422, str(error)) from error
        async with store.lock(session_id), generation_slot:
            session = load(session_id)
            try:
                sessions.require_interview(store, session)
                prompt = vocabulary_prompt(session.case.persona.name)
                result = await recognizer(settings).transcribe(audio, prompt)
                _, event = sessions.record_transcription(
                    store, session, result, audio.duration_ms, prompt
                )
            except sessions.SessionError as error:
                raise HTTPException(409, str(error)) from error
            except SpeechError as error:
                raise HTTPException(503, str(error)) from error
        return TranscriptionView(
            transcription_id=event.id,
            text=event.text,
            audio_ms=event.audio_ms,
            asr_ms=event.asr_ms,
        )

    @router.post(
        "/{session_id}/speech",
        response_model=SpeechView,
        responses={
            409: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    async def speak(session_id: str, body: SpeechRequest, request: Request) -> SpeechView:
        """Synthesise a sentence the character has said, or one of the case's authored
        hesitations, in the given voice. Not stored."""

        async def work() -> SpeechView:
            # Waits for a turn in progress to be saved, so only released text is voiced.
            async with store.lock(session_id):
                session = load(session_id)
                lines = [reply for _, reply in session.history()]
                fillers = {h for stage in session.case.affect_stages for h in stage.hesitations}
                if body.text.strip() not in fillers and not spoken_by_character(body.text, lines):
                    raise HTTPException(422, "Only the character's own lines can be voiced")
            try:
                voice = synthesizer(settings, body.voice)
                # Never synthesise while the language model generates (they share the GPU).
                async with generation_slot:
                    result = await voice.synthesize(body.text.strip(), body.voice)
            except SynthesisError as error:
                status = {"disabled": 409, "unknown_voice": 422}.get(error.code, 503)
                raise HTTPException(status, str(error)) from error
            return SpeechView(
                audio_wav_base64=base64.b64encode(result.wav).decode("ascii"),
                words=result.words,
                word_times_ms=result.word_times,
                word_durations_ms=result.word_durations,
                visemes=result.visemes,
                viseme_times_ms=result.viseme_times,
                viseme_durations_ms=result.viseme_durations,
                voice=result.voice,
                model=result.model,
                synthesis_ms=result.synthesis_ms,
            )

        try:
            async with asyncio.timeout(2 * settings.model_timeout_seconds + 5):
                return await until_disconnect(request, work())
        except TimeoutError as error:
            raise HTTPException(503, "Local speech synthesis timed out") from error

    @router.post(
        "/{session_id}/interruptions",
        status_code=204,
        responses={409: {"model": ErrorResponse}},
    )
    async def interrupted(session_id: str, body: InterruptionRequest) -> None:
        """Record that the candidate spoke over the character (hands-free conversation)."""
        async with store.lock(session_id):
            try:
                sessions.record_interruption(store, load(session_id), body.during, body.heard_ms)
            except sessions.SessionError as error:
                raise HTTPException(409, str(error)) from error

    @router.get(
        "/{session_id}/debrief", response_model=Debrief, responses={409: {"model": ErrorResponse}}
    )
    async def read_debrief(session_id: str) -> Debrief:
        async with store.lock(session_id):
            session = sessions.expire(store, load(session_id))
            if session.phase != "ended":
                raise HTTPException(409, "Feedback is available once the station has ended")
            return debrief(session)

    @router.post("/{session_id}/end", response_model=Debrief)
    async def finish(session_id: str) -> Debrief:
        async with store.lock(session_id):
            session = load(session_id)
            if session.phase == "reading":
                raise HTTPException(409, "The interview has not begun")
            return debrief(sessions.end(store, session))

    return router
