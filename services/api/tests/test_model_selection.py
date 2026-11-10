import json

import httpx
import pytest

from psychiatry_api.config import ROOT
from psychiatry_api.models import selection
from psychiatry_api.models.errors import ModelError
from psychiatry_api.models.local import LocalLanguageModel
from psychiatry_api.models.transport import request_model


def test_backend_selection_is_explicit(settings):
    local = settings.model_copy(update={"model_backend": "local"})
    assert isinstance(selection.language_model(local), LocalLanguageModel)
    with pytest.raises(ModelError):
        selection.language_model(settings)
    with pytest.raises(ModelError):
        selection.language_model(
            local.model_copy(update={"llm_base_url": "https://example.invalid"})
        )


def test_legacy_qa_backend_variable_is_still_accepted(monkeypatch):
    from psychiatry_api.config import Settings

    monkeypatch.setenv("QA_BACKEND", "local")
    assert Settings(_env_file=None).model_backend == "local"


@pytest.mark.parametrize(
    "incorrect", [None, "model_path", "model_alias", "build_info", "total_slots", "context"]
)
async def test_native_identity_checks_file_build_slots_and_context(
    settings, monkeypatch, incorrect
):
    runtime = json.loads((ROOT / "config/native-runtime.json").read_text())
    props = {
        "model_alias": settings.llm_model_id,
        "model_path": str(settings.native_model_home / "models/Qwen3-4B-Q4_K_M.gguf"),
        "build_info": f"{runtime['build']}-{runtime['commit'][:9]}",
        "total_slots": 1,
        "default_generation_settings": {"n_ctx": 4096},
    }
    if incorrect == "context":
        props["default_generation_settings"]["n_ctx"] = 2048
    elif incorrect:
        props[incorrect] = "wrong"
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=props))
    monkeypatch.setattr(
        selection,
        "request_model",
        lambda url, **kwargs: request_model(url, transport=transport, **kwargs),
    )
    if incorrect:
        with pytest.raises(ModelError, match="properties"):
            await selection.verify_service(settings)
    else:
        await selection.verify_service(settings)


async def test_unknown_revision_is_rejected_before_contacting_runtime(settings, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Unregistered revision must not reach runtime")

    monkeypatch.setattr(selection, "request_model", forbidden)
    with pytest.raises(ModelError, match="revision"):
        await selection.verify_service(settings.model_copy(update={"llm_model_revision": "wrong"}))


async def test_embedding_identity_uses_its_own_pinned_model(settings, monkeypatch):
    runtime = json.loads((ROOT / "config/native-runtime.json").read_text())
    props = {
        "model_alias": settings.embedding_model_id,
        "model_path": str(settings.native_model_home / "models/Qwen3-Embedding-0.6B-Q8_0.gguf"),
        "build_info": f"{runtime['build']}-{runtime['commit'][:9]}",
        "total_slots": 1,
        "default_generation_settings": {"n_ctx": 4096},
    }
    seen = []

    def respond(request):
        seen.append(str(request.url))
        return httpx.Response(200, json=props)

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(
        selection,
        "request_model",
        lambda url, **kwargs: request_model(url, transport=transport, **kwargs),
    )
    await selection.verify_embedding_service(settings)
    assert seen == ["http://127.0.0.1:8181/props"]
    props["model_alias"] = settings.llm_model_id
    with pytest.raises(ModelError, match="properties"):
        await selection.verify_embedding_service(settings)
    model = selection.embedding_model(settings)
    assert model.config.dimensions == 1024 and model.config.normalization == "l2-v1"
