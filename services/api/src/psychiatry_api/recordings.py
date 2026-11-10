"""Opt-in speech recordings for the ASR evaluation (Phase 4).

The application never stores interview audio. This separate, off-by-default tool records
consenting speakers reading the labelled evaluation prompts, saving WAV files and a
manifest under data/recordings/<speaker>/ (ignored by git) for `npm run eval:asr --manifest`.
"""

from typing import Annotated

import yaml
from fastapi import APIRouter, HTTPException, Query, Request

from psychiatry_api.config import ROOT, Settings
from psychiatry_api.domain import Contract
from psychiatry_api.evaluation.interpreter import speech_labels
from psychiatry_api.schemas import ErrorResponse
from psychiatry_api.speech import MAX_BYTES, SpeechError, validate_wav

Speaker = Annotated[str, Query(pattern=r"^[a-z0-9][a-z0-9-]{1,30}$")]
CONSENT = (
    "I agree to my voice being recorded reading these fictional prompts. The recordings stay "
    "on this computer and are used only to measure speech-recognition accuracy for this "
    "project. I can delete them at any time from data/recordings."
)


class Prompt(Contract):
    item: int
    case_id: str
    text: str


class RecordingPrompts(Contract):
    enabled: bool
    consent: str
    prompts: tuple[Prompt, ...]


class Saved(Contract):
    item: int
    recorded: int
    duration_ms: int


def prompts() -> tuple[Prompt, ...]:
    rows = [(label.case_id, item.utterance) for label in speech_labels() for item in label.items]
    return tuple(Prompt(item=i, case_id=c, text=t) for i, (c, t) in enumerate(rows, 1))


def recording_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/recordings", tags=["Evaluation recordings"])

    @router.get("/prompts", response_model=RecordingPrompts)
    def list_prompts() -> RecordingPrompts:
        return RecordingPrompts(
            enabled=settings.recordings_enabled, consent=CONSENT, prompts=prompts()
        )

    @router.post(
        "",
        response_model=Saved,
        responses={
            409: {"model": ErrorResponse},
            413: {"model": ErrorResponse},
            422: {"model": ErrorResponse},
        },
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"audio/wav": {"schema": {"type": "string", "format": "binary"}}},
            }
        },
    )
    async def save(
        request: Request, speaker: Speaker, item: int = Query(ge=1), consent: bool = Query()
    ) -> Saved:
        if not settings.recordings_enabled:
            raise HTTPException(409, "Recording is turned off (set RECORDINGS_ENABLED=true)")
        if not consent:
            raise HTTPException(409, "Consent is required before recording")
        lookup = {p.item: p for p in prompts()}
        if item not in lookup:
            raise HTTPException(422, "Unknown prompt")
        if int(request.headers.get("content-length") or 0) > MAX_BYTES:
            raise HTTPException(413, "Recordings are limited to 60 seconds")
        try:
            audio = validate_wav(await request.body())
        except SpeechError as error:
            raise HTTPException(413 if error.code == "too_long" else 422, str(error)) from error
        folder = settings.recordings_path / speaker
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{item:03d}.wav"
        path.write_bytes(audio.data)
        manifest = folder / "manifest.yaml"
        items = yaml.safe_load(manifest.read_text())["items"] if manifest.exists() else []
        entry = {
            "audio": str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
            "reference": lookup[item].text,
            "case_id": lookup[item].case_id,
            "voice": speaker,
        }
        items = [i for i in items if i["audio"] != entry["audio"]] + [entry]
        manifest.write_text(yaml.safe_dump({"items": items}, sort_keys=False, allow_unicode=True))
        return Saved(item=item, recorded=len(items), duration_ms=audio.duration_ms)

    return router
