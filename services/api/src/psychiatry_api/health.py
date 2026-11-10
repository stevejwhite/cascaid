import asyncio
import json
from datetime import UTC, datetime

import httpx

from psychiatry_api.case_versions import drift
from psychiatry_api.cases import load_cases
from psychiatry_api.config import ROOT, Settings
from psychiatry_api.models.selection import verify_embedding_service, verify_service
from psychiatry_api.models.student import running_student
from psychiatry_api.models.transport import validate_endpoint
from psychiatry_api.schemas import Readiness, ServiceCheck
from psychiatry_api.sources import load_registry
from psychiatry_api.speech import running_model
from psychiatry_api.synthesis import running_service


async def model_check(base_url: str, model_id: str, timeout: float) -> ServiceCheck:
    try:
        validate_endpoint(base_url)
        # A generic 200/health response could belong to another local service.
        # Require the configured served model ID, not simply an open port.
        async with (
            asyncio.timeout(timeout),
            httpx.AsyncClient(follow_redirects=False, trust_env=False, timeout=timeout) as client,
        ):
            response = await client.get(f"{base_url.rstrip('/')}/models")
            response.raise_for_status()
            models = response.json().get("data", [])
            if any(item.get("id") == model_id for item in models):
                return ServiceCheck(status="ready", detail="Configured model is served locally.")
        return ServiceCheck(status="unavailable", detail="Configured model is not served here.")
    except Exception:
        return ServiceCheck(status="unavailable", detail="Local model service is not ready.")


async def generation_check(settings: Settings) -> ServiceCheck:
    check = await model_check(
        settings.llm_base_url, settings.llm_model_id, settings.readiness_timeout_seconds
    )
    if settings.model_backend == "local" and check.status == "ready":
        try:
            await verify_service(settings)
        except Exception:
            return ServiceCheck(status="unavailable", detail="Native model identity check failed.")
    return check


def registry_check(settings: Settings) -> ServiceCheck:
    try:
        registry = load_registry(settings.source_registry_path)
    except Exception:
        return ServiceCheck(status="invalid", detail="Source registry is invalid or unavailable.")
    return ServiceCheck(status="ready", detail=f"{len(registry.sources)} sources registered.")


def cases_check(settings: Settings) -> ServiceCheck:
    try:
        cases = load_cases(settings.cases_path)
    except Exception as error:
        return ServiceCheck(status="invalid", detail=f"Case failed validation: {error}")
    if not cases:
        return ServiceCheck(status="empty", detail="No station cases found.")
    detail = f"{len(cases)} station case{'' if len(cases) == 1 else 's'} available."
    if settings.student_backend == "local":
        model = (
            pinned_model("reranker")
            if settings.topic_decider == "reranker"
            else pinned_model("student")
        )
        if note := drift(settings.cases_path, model):
            detail += f" {note}"
    return ServiceCheck(status="ready", detail=detail)


def pinned_model(kind: str) -> str:
    return json.loads((ROOT / "config/finetune.json").read_text())[kind]["name"]


async def speech_check(settings: Settings) -> ServiceCheck:
    if settings.speech_backend == "off":
        return ServiceCheck(status="disabled", detail="Speech input is off; typing works.")
    if settings.speech_backend == "fake":
        return ServiceCheck(status="ready", detail="Fake transcription for development.")
    model = running_model(settings.speech_state_file)
    if model is None:
        return ServiceCheck(status="unavailable", detail="Start it with npm run speech:start.")
    try:
        validate_endpoint(settings.asr_base_url)
        async with httpx.AsyncClient(
            trust_env=False, timeout=settings.readiness_timeout_seconds
        ) as client:
            response = await client.get(f"{settings.asr_base_url.rstrip('/')}/health")
            response.raise_for_status()
    except Exception:
        return ServiceCheck(status="unavailable", detail="Local speech server is not ready.")
    return ServiceCheck(status="ready", detail=f"whisper.cpp is serving {model} locally.")


async def voice_check(settings: Settings) -> ServiceCheck:
    if settings.tts_backend == "off":
        return ServiceCheck(
            status="disabled", detail="Character voice is off; browser voices work."
        )
    if settings.tts_backend == "fake":
        return ServiceCheck(status="ready", detail="Silent fake voice for development.")
    service = running_service(settings.tts_state_file)
    if service is None:
        return ServiceCheck(status="unavailable", detail="Start it with npm run tts:start.")
    try:
        validate_endpoint(settings.tts_base_url)
        async with httpx.AsyncClient(
            trust_env=False, timeout=settings.readiness_timeout_seconds
        ) as client:
            response = await client.post(f"{settings.tts_base_url.rstrip('/')}/v1/hello")
            response.raise_for_status()
    except Exception:
        return ServiceCheck(status="unavailable", detail="Local speech synthesis is not ready.")
    voices = ", ".join(service["voices"])
    return ServiceCheck(status="ready", detail=f"Kokoro-82M is serving {voices} locally.")


async def readiness(settings: Settings) -> Readiness:
    generation, speech, voice = await asyncio.gather(
        generation_check(settings), speech_check(settings), voice_check(settings)
    )
    registry, cases = registry_check(settings), cases_check(settings)
    ready = registry.status == cases.status == "ready" and (
        settings.model_backend == "fake" or generation.status == "ready"
    )
    if settings.production:
        ready = ready and speech.status == voice.status == "ready"
        ready = ready and await production_interpreters_ready(settings)
    return Readiness(
        status="ready" if ready else "not_ready",
        model_backend=settings.model_backend,
        speech_backend=settings.speech_backend,
        tts_backend=settings.tts_backend,
        checked_at=datetime.now(UTC),
        registry=registry,
        cases=cases,
        generation=generation,
        speech=speech,
        voice=voice,
    )


async def production_interpreters_ready(settings: Settings) -> bool:
    """Production cannot silently lose a classifier/student service and still be ready."""
    try:
        await verify_embedding_service(settings)
        pinned = json.loads((ROOT / "config/finetune.json").read_text())["student"]
        state = running_student(settings.student_state_file)
        if state != {
            "model": pinned["name"],
            "format_version": pinned["format_version"],
            "weights_sha256": pinned["weights_sha256"],
        }:
            return False
        validate_endpoint(settings.student_base_url)
        async with httpx.AsyncClient(
            trust_env=False, timeout=settings.readiness_timeout_seconds
        ) as client:
            response = await client.get(f"{settings.student_base_url}/health")
            response.raise_for_status()
        return True
    except Exception:
        return False
