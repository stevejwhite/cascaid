"""Station sessions as append-only JSONL event logs (one file per session).

The log is the research record: it snapshots the case, and records every turn's
interpretation, disclosures, guard flags and per-stage timings. State is rebuilt by
replaying events, so the file alone reproduces a session.
"""

import asyncio
import hashlib
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, TypeAdapter

from psychiatry_api.cases import Case, Slug
from psychiatry_api.config import Settings
from psychiatry_api.domain import Contract
from psychiatry_api.models.errors import ModelError
from psychiatry_api.roleplay.calls import ModelCall
from psychiatry_api.roleplay.disclosure import (
    DisclosureState,
    Interpretation,
    apply,
    rapport_after,
)
from psychiatry_api.roleplay.interpret import Interpreter
from psychiatry_api.roleplay.respond import RolePlayer, turn_seed

LOG_VERSION = "casc-session-v1"
# Allow for network and model latency on the final turn before refusing new turns.
GRACE_SECONDS = 15
SessionId = Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]


def now() -> datetime:
    return datetime.now(UTC)


class Started(Contract):
    type: Literal["started"] = "started"
    log_version: str = LOG_VERSION
    session_id: SessionId
    at: AwareDatetime
    case: Case
    case_sha256: str
    backend: Literal["fake", "local"]
    interpreter: str
    interpreter_prompt: str | None
    role_player: str
    role_player_prompt: str | None


class Began(Contract):
    type: Literal["began"] = "began"
    at: AwareDatetime
    opening: str


class Transcribed(Contract):
    """Speech recognised during the interview. The audio itself is never stored."""

    type: Literal["transcribed"] = "transcribed"
    id: str
    at: AwareDatetime
    text: str
    raw_text: str
    recognizer: str
    prompt: str | None
    audio_ms: int
    asr_ms: int


class Turn(Contract):
    type: Literal["turn"] = "turn"
    index: int
    at: AwareDatetime
    candidate: str
    input: Literal["typed", "speech"] = "typed"
    transcription_id: str | None = None
    # Whether the candidate changed the recognised text before sending it.
    edited: bool | None = None
    focus: str | None
    asked: tuple[str, ...]
    rapport: bool
    # Graded empathy (0-2) and confrontation from casc-interpret-v2; None in older logs,
    # where rapport alone was recorded (replayed as empathy 1).
    empathy: int | None = None
    confrontational: bool = False
    # The running rapport level after this turn.
    rapport_level: float | None = None
    # Cascade interpreter only: which route decided topics and tone, and the classifiers'
    # confidence in their best answers.
    # student: the fine-tuned student interpreter (classifiers unsure, before Qwen).
    topic_route: Literal["classifier", "student", "reranker", "model"] | None = None
    topic_confidence: float | None = None
    # The topic classifier's best guess, even when not confident (fact ID or "none").
    topic_leaning: str | None = None
    tone_route: Literal["classifier", "model"] | None = None
    tone_confidence: float | None = None
    unlocked: tuple[str, ...]
    answering: tuple[str, ...]
    deferred: tuple[str, ...]
    touched: tuple[str, ...] = ()
    # The character's affect stage for this reply, when the case defines stages.
    affect_stage: str | None = None
    # A question the character asked at the end of this reply (its ID in the case).
    question: str | None = None
    # Whether this utterance answered the character's previous question (None: none pending).
    answered: bool | None = None
    reply: str
    seed: int
    flags: tuple[str, ...]
    calls: tuple[ModelCall, ...]
    interpret_ms: int
    respond_ms: int
    total_ms: int
    # Time from the start of the turn until the first reply sentence was released.
    first_sentence_ms: int | None = None


class TurnFailed(Contract):
    type: Literal["turn_failed"] = "turn_failed"
    index: int
    at: AwareDatetime
    candidate: str
    error: str
    calls: tuple[ModelCall, ...]


class Interrupted(Contract):
    """The candidate spoke over the character (hands-free conversation).

    The reply is already in the transcript; this records when it was cut short and how much
    of its audio had been heard. during: speaking (the voice was playing) or thinking (the
    reply was still being prepared, and is then not read aloud).
    """

    type: Literal["interrupted"] = "interrupted"
    at: AwareDatetime
    after_turn: int = Field(ge=0)
    during: Literal["speaking", "thinking"]
    heard_ms: int = Field(ge=0, le=600_000)


class Ended(Contract):
    type: Literal["ended"] = "ended"
    at: AwareDatetime
    reason: Literal["candidate_ended", "time_up"]


Event = Annotated[
    Started | Began | Transcribed | Turn | TurnFailed | Interrupted | Ended,
    Field(discriminator="type"),
]
EVENT = TypeAdapter(Event)


class SessionError(ValueError):
    """A request that is invalid for the session's current phase."""


class Session:
    def __init__(self, events: list):
        if not events or not isinstance(events[0], Started):
            raise ValueError("Session log must begin with a started event")
        self.events = events

    @property
    def started(self) -> Started:
        return self.events[0]

    @property
    def case(self) -> Case:
        return self.started.case

    def first(self, kind):
        return next((e for e in self.events if isinstance(e, kind)), None)

    @property
    def turns(self) -> list[Turn]:
        return [e for e in self.events if isinstance(e, Turn)]

    def transcription(self, transcription_id: str) -> Transcribed:
        """An unused transcription from this session, or a SessionError."""
        found = next(
            (e for e in self.events if isinstance(e, Transcribed) and e.id == transcription_id),
            None,
        )
        if found is None:
            raise SessionError("Unknown transcription for this session")
        if any(t.transcription_id == transcription_id for t in self.turns):
            raise SessionError("This transcription has already been sent")
        return found

    @property
    def phase(self) -> Literal["reading", "interview", "ended"]:
        if self.first(Ended):
            return "ended"
        return "interview" if self.first(Began) else "reading"

    @property
    def deadline(self) -> datetime | None:
        began = self.first(Began)
        return began.at + timedelta(seconds=self.case.timing.interview_seconds) if began else None

    def state(self) -> DisclosureState:
        unlocked = tuple(i for turn in self.turns for i in turn.unlocked)
        touched = tuple(i for turn in self.turns for i in turn.touched)
        level = 0.0
        for turn in self.turns:
            empathy = turn.empathy if turn.empathy is not None else int(turn.rapport)
            level = rapport_after(
                level, Interpretation(empathy=empathy, confrontational=turn.confrontational)
            )
        confronted = bool(self.turns) and self.turns[-1].confrontational
        return DisclosureState(
            unlocked=unlocked, rapport=level, touched=touched, confronted=confronted
        )

    def pending_question(self) -> str | None:
        """The question the character asked at the end of its last reply, if any."""
        if self.turns and self.turns[-1].question:
            asked = self.turns[-1].question
            return next(q.text for q in self.case.questions if q.id == asked)
        return None

    def due_question(self, state: DisclosureState, seconds: float):
        """The first not-yet-asked case question whose trigger has been met."""
        asked = {t.question for t in self.turns}
        revealed = set(state.unlocked) | set(state.touched)
        for question in self.case.questions:
            if question.id in asked:
                continue
            if question.after_fact and question.after_fact in revealed:
                return question
            if question.after_seconds is not None and seconds >= question.after_seconds:
                return question
        return None

    def history(self) -> list[tuple[str, str]]:
        began = self.first(Began)
        opening = [("", began.opening)] if began else []
        return opening + [(t.candidate, t.reply) for t in self.turns]


class SessionStore:
    def __init__(self, root: Path):
        self.root = root
        self.locks: dict[str, asyncio.Lock] = {}

    def path(self, session_id: str) -> Path:
        TypeAdapter(SessionId).validate_python(session_id)
        return self.root / f"{session_id}.jsonl"

    def lock(self, session_id: str) -> asyncio.Lock:
        return self.locks.setdefault(session_id, asyncio.Lock())

    def load(self, session_id: str) -> Session:
        path = self.path(session_id)
        if not path.exists():
            raise KeyError(session_id)
        lines = path.read_text().splitlines()
        return Session([EVENT.validate_json(line) for line in lines if line.strip()])

    def append(self, session_id: str, event) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with self.path(session_id).open("a") as handle:
            handle.write(event.model_dump_json() + "\n")


def case_digest(settings: Settings, case_id: str) -> str:
    return hashlib.sha256((settings.cases_path / f"{case_id}.yaml").read_bytes()).hexdigest()


def create(
    store: SessionStore,
    settings: Settings,
    case: Case,
    interpreter: Interpreter,
    role_player: RolePlayer,
) -> Session:
    TypeAdapter(Slug).validate_python(case.id)
    started = Started(
        session_id=uuid.uuid4().hex,
        at=now(),
        case=case,
        case_sha256=case_digest(settings, case.id),
        backend=settings.model_backend,
        interpreter=interpreter.id,
        interpreter_prompt=interpreter.prompt_version,
        role_player=role_player.id,
        role_player_prompt=role_player.prompt_version,
    )
    store.append(started.session_id, started)
    return Session([started])


def expire(store: SessionStore, session: Session) -> Session:
    """End an interview whose time (plus grace) has run out."""
    deadline = session.deadline
    if (
        session.phase == "interview"
        and deadline
        and now() > deadline + timedelta(seconds=GRACE_SECONDS)
    ):
        ended = Ended(at=now(), reason="time_up")
        store.append(session.started.session_id, ended)
        return Session([*session.events, ended])
    return session


def begin(store: SessionStore, session: Session) -> Session:
    if session.phase != "reading":
        raise SessionError("The interview has already begun")
    began = Began(at=now(), opening=session.case.persona.opening_statement)
    store.append(session.started.session_id, began)
    return Session([*session.events, began])


def end(store: SessionStore, session: Session) -> Session:
    session = expire(store, session)
    if session.phase == "ended":
        return session
    ended = Ended(at=now(), reason="candidate_ended")
    store.append(session.started.session_id, ended)
    return Session([*session.events, ended])


def require_interview(store: SessionStore, session: Session) -> Session:
    session = expire(store, session)
    if session.phase == "reading":
        raise SessionError("Begin the interview before speaking")
    if session.phase == "ended":
        raise SessionError("This station has ended")
    return session


def record_transcription(
    store: SessionStore, session: Session, transcription, audio_ms: int, prompt: str | None
) -> tuple[Session, Transcribed]:
    session = require_interview(store, session)
    event = Transcribed(
        id=uuid.uuid4().hex,
        at=now(),
        text=transcription.text,
        raw_text=transcription.raw_text,
        recognizer=transcription.model,
        prompt=prompt,
        audio_ms=audio_ms,
        asr_ms=transcription.asr_ms,
    )
    store.append(session.started.session_id, event)
    return Session([*session.events, event]), event


def record_interruption(
    store: SessionStore, session: Session, during: str, heard_ms: int
) -> Interrupted:
    session = require_interview(store, session)
    event = Interrupted(at=now(), after_turn=len(session.turns), during=during, heard_ms=heard_ms)
    store.append(session.started.session_id, event)
    return event


async def take_turn(
    store: SessionStore,
    session: Session,
    utterance: str,
    interpreter: Interpreter,
    role_player: RolePlayer,
    transcription_id: str | None = None,
) -> Session:
    """One turn, start to finish (evaluation and the non-streaming endpoint)."""
    async for kind, payload in take_turn_stream(
        store, session, utterance, interpreter, role_player, transcription_id
    ):
        if kind == "done":
            return payload
    raise RuntimeError("Turn ended without a result")


async def take_turn_stream(
    store: SessionStore,
    session: Session,
    utterance: str,
    interpreter: Interpreter,
    role_player: RolePlayer,
    transcription_id: str | None = None,
) -> AsyncIterator[tuple[str, object]]:
    """Yield ("pace", slow) first, then ("sentence", text) as the reply is released, then
    ("done", updated session). slow: the turn will wait for the language model, so the
    character may hesitate (presentation only).

    The turn is logged only once the reply is complete; an abandoned stream logs nothing.
    """
    session = require_interview(store, session)
    spoken = session.transcription(transcription_id) if transcription_id else None
    session_id, case = session.started.session_id, session.case
    index = len(session.turns) + len([e for e in session.events if isinstance(e, TurnFailed)])
    history, state = session.history(), session.state()
    pending = session.pending_question()
    started_at, clock = now(), perf_counter()
    forecast = getattr(interpreter, "forecast", None)
    if forecast is not None:
        yield "pace", await forecast(case, utterance, pending, history=history)
    interpretation, calls, flags = await interpreter.interpret(
        case, state, history, utterance, pending
    )
    interpret_ms = round((perf_counter() - clock) * 1000)
    disclosure = apply(case, state, interpretation)
    seed = turn_seed(session_id, index)
    clock = perf_counter()
    first_sentence_ms, result = None, None
    try:
        async for kind, payload in role_player.respond_stream(
            case, disclosure, history, utterance, seed
        ):
            if kind == "sentence":
                if first_sentence_ms is None:
                    first_sentence_ms = interpret_ms + round((perf_counter() - clock) * 1000)
                yield "sentence", payload
            else:
                result = payload
    except ModelError as error:
        failed = TurnFailed(
            index=index,
            at=started_at,
            candidate=utterance,
            error=error.code,
            calls=tuple(calls)
            + (ModelCall(prompt_version=role_player.prompt_version or "", status=error.code),),
        )
        store.append(session_id, failed)
        raise
    reply, reply_calls, reply_flags = result
    # An authored question is appended verbatim after the guarded reply (one per turn).
    began = session.first(Began)
    question = session.due_question(disclosure.state, (started_at - began.at).total_seconds())
    if question:
        reply = f"{reply} {question.text}"
        yield "sentence", question.text
    respond_ms = round((perf_counter() - clock) * 1000)
    turn = Turn(
        index=index,
        at=started_at,
        candidate=utterance,
        input="speech" if spoken else "typed",
        transcription_id=transcription_id,
        edited=None if spoken is None else utterance != spoken.text,
        focus=interpretation.focus,
        asked=tuple(sorted(interpretation.asked)),
        rapport=interpretation.rapport,
        empathy=interpretation.empathy,
        confrontational=interpretation.confrontational,
        rapport_level=disclosure.state.rapport,
        topic_route=interpretation.topic_route,
        topic_confidence=interpretation.topic_confidence,
        topic_leaning=interpretation.topic_leaning,
        tone_route=interpretation.tone_route,
        tone_confidence=interpretation.tone_confidence,
        touched=disclosure.touched,
        affect_stage=disclosure.stage.id if disclosure.stage else None,
        question=question.id if question else None,
        answered=interpretation.answered if pending else None,
        unlocked=disclosure.unlocked,
        answering=disclosure.answering,
        deferred=disclosure.deferred,
        reply=reply,
        seed=seed,
        flags=tuple(flags + reply_flags),
        calls=tuple(calls + reply_calls),
        interpret_ms=interpret_ms,
        respond_ms=respond_ms,
        total_ms=interpret_ms + respond_ms,
        first_sentence_ms=first_sentence_ms,
    )
    store.append(session_id, turn)
    yield "done", Session([*session.events, turn])
