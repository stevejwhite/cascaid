"""Resolve the model used by an evaluation: the registered model or a pinned experiment."""

import json

import httpx

from psychiatry_api.config import ROOT, Settings
from psychiatry_api.models.contracts import LanguageModel
from psychiatry_api.models.local import LocalConfig, LocalLanguageModel
from psychiatry_api.models.selection import language_model, runtime_identity, verify_service

REGISTERED = "registered"
EXPERIMENTS = ROOT / "config/experiment-models.json"
EXPERIMENT_STATE = ROOT / "artifacts/m4/experiment-state.json"


async def resolve(settings: Settings, name: str) -> tuple[LanguageModel, str]:
    """Return a model and a label for reports; refuse anything unpinned or unverified."""
    timeout_ms = int(settings.model_timeout_seconds * 1000)
    if name == REGISTERED:
        local = settings.model_copy(update={"model_backend": "local"})
        await verify_service(local)
        return language_model(local), settings.llm_model_id
    config = json.loads(EXPERIMENTS.read_text())
    model = next((m for m in config["models"] if m["id"] == name), None)
    if model is None:
        raise SystemExit(f"Unknown model {name!r}; use 'registered' or an id in {EXPERIMENTS.name}")
    try:
        state = json.loads(EXPERIMENT_STATE.read_text())
    except OSError as error:
        raise SystemExit(f"Start it first: npm run experiment:start -- {name}") from error
    if state.get("model") != name or state.get("sha256") != model["checksum_sha256"]:
        raise SystemExit(f"The running experiment server is not {name}")
    base_url = f"http://127.0.0.1:{config['port']}/v1"
    async with httpx.AsyncClient(trust_env=False, timeout=5) as client:
        props = (await client.get(f"http://127.0.0.1:{config['port']}/props")).json()
    if props.get("model_alias") != model["alias"]:
        raise SystemExit("Experiment server identity does not match its state file")
    return (
        LocalLanguageModel(
            LocalConfig(
                base_url=base_url,
                model_id=model["alias"],
                revision=model["revision"],
                runtime=runtime_identity(),
                quantisation="Q4_K_M",
                timeout_ms=timeout_ms,
            )
        ),
        model["alias"],
    )
