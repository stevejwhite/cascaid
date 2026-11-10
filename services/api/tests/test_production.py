import pytest
from pydantic import ValidationError

from psychiatry_api import health
from psychiatry_api.config import Settings
from psychiatry_api.schemas import ServiceCheck


def production(tmp_path, **overrides):
    return Settings(
        _env_file=None,
        **{
            "deployment_profile": "production-local",
            "model_backend": "local",
            "speech_backend": "local",
            "tts_backend": "local",
            "student_backend": "local",
            "sessions_path": tmp_path / "sessions",
            "classifier_cache": tmp_path / "cache",
            **overrides,
        },
    )


@pytest.mark.parametrize(
    "key", ["model_backend", "speech_backend", "tts_backend", "student_backend"]
)
def test_production_rejects_fake_or_missing_services(tmp_path, key):
    with pytest.raises(ValidationError):
        production(tmp_path, **{key: "fake" if key != "student_backend" else "off"})


def test_production_rejects_recordings_remote_models_and_implicit_profile(tmp_path, monkeypatch):
    with pytest.raises(ValidationError):
        production(tmp_path, recordings_enabled=True)
    with pytest.raises(ValidationError):
        production(tmp_path, llm_base_url="https://example.org/v1")
    with pytest.raises(ValidationError):
        production(tmp_path, deployment_profile="online")
    monkeypatch.setenv("CASCAID_PRODUCTION_ACTIVE", "1")
    with pytest.raises(ValidationError):
        production(tmp_path, deployment_profile="development")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "missing", ["speech_check", "voice_check", "production_interpreters_ready"]
)
async def test_production_readiness_requires_every_service(tmp_path, monkeypatch, missing):
    async def ready(*_):
        return ServiceCheck(status="ready", detail="test")

    async def unavailable(*_):
        return ServiceCheck(status="unavailable", detail="test")

    async def interpreters(*_):
        return missing != "production_interpreters_ready"

    for name in ("generation_check", "speech_check", "voice_check"):
        monkeypatch.setattr(health, name, unavailable if name == missing else ready)
    monkeypatch.setattr(health, "production_interpreters_ready", interpreters)
    result = await health.readiness(production(tmp_path))
    assert result.status == "not_ready"
