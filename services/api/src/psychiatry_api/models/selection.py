"""One configuration boundary for local models; no automatic provider fallback."""

import json
from pathlib import Path

import httpx

from psychiatry_api.config import ROOT, Settings
from psychiatry_api.models.errors import ModelError
from psychiatry_api.models.local import LocalConfig, LocalEmbeddingModel, LocalLanguageModel
from psychiatry_api.models.transport import request_model


def runtime_identity() -> str:
    record = json.loads((ROOT / "config/native-runtime.json").read_text())
    return f"llama.cpp {record['build']} {record['commit']} Metal"


def language_model(settings: Settings) -> LocalLanguageModel:
    if settings.model_backend != "local":
        raise ModelError("invalid_request", "Local generation must be explicitly selected")
    return LocalLanguageModel(
        LocalConfig(
            base_url=settings.llm_base_url,
            model_id=settings.llm_model_id,
            revision=settings.llm_model_revision,
            runtime=runtime_identity(),
            quantisation="Q4_K_M",
            timeout_ms=int(settings.model_timeout_seconds * 1000),
        )
    )


async def verify_service(settings: Settings) -> None:
    """Match the generation server's properties to the pinned installation attested by
    models:start.

    Full file hashes are checked at startup, not on every request. Props must report
    that exact file/build/context. This is a local development identity check, not
    remote attestation or a defence against a malicious local account.
    """
    await verify_runtime(
        settings,
        "generation",
        settings.llm_base_url,
        settings.llm_model_id,
        settings.llm_model_revision,
    )


async def verify_embedding_service(settings: Settings) -> None:
    """The same identity check for the embedding server."""
    await verify_runtime(
        settings,
        "embedding",
        settings.embedding_base_url,
        settings.embedding_model_id,
        settings.embedding_model_revision,
    )


async def verify_runtime(
    settings: Settings, kind: str, base_url: str, model_id: str, revision: str
) -> None:
    record = json.loads((ROOT / "config/native-runtime.json").read_text())
    register = json.loads((ROOT / "config/model-register.json").read_text())
    model = next(row for row in register["models"] if row["kind"] == kind)
    artifact = model["candidate_artifacts"][0]
    if (
        revision != model["upstream_revision"]
        or model_id != f"{model['upstream_model_id']}:{artifact['quantisation']}"
    ):
        raise ModelError("model_unavailable", "Unverified model revision")
    props_url = str(httpx.URL(base_url).copy_with(path="/props"))
    async with request_model(props_url, timeout_ms=2000) as response:
        props = json.loads(await response.aread())
    expected_file = settings.native_model_home / "models" / artifact["filename"]
    if (
        Path(props.get("model_path", "")).resolve() != expected_file.resolve()
        or props.get("build_info") != f"{record['build']}-{record['commit'][:9]}"
        or props.get("model_alias") != model_id
        or props.get("total_slots") != record["parallel_slots"]
        or props.get("default_generation_settings", {}).get("n_ctx") != record["context_tokens"]
    ):
        raise ModelError(
            "model_unavailable", "Runtime properties do not match the pinned configuration"
        )


def embedding_model(settings: Settings) -> LocalEmbeddingModel:
    register = json.loads((ROOT / "config/model-register.json").read_text())
    model = next(row for row in register["models"] if row["kind"] == "embedding")
    return LocalEmbeddingModel(
        LocalConfig(
            base_url=settings.embedding_base_url,
            model_id=settings.embedding_model_id,
            revision=settings.embedding_model_revision,
            runtime=runtime_identity(),
            quantisation=model["candidate_artifacts"][0]["quantisation"],
            dimensions=model["embedding_dimensions"],
            normalization=model["normalization_version"],
            timeout_ms=int(settings.model_timeout_seconds * 1000),
        )
    )
