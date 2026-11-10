from psychiatry_api.domain import Contract
from psychiatry_api.models.contracts import GenerationResult


class ModelCall(Contract):
    """Per-call measurements kept in the session log; no prompt text is stored."""

    prompt_version: str
    status: str = "completed"
    model_id: str | None = None
    model_revision: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    first_token_ms: int | None = None
    total_ms: int | None = None
    finish_reason: str | None = None
    # Prompt tokens the runtime reused from its cache, and its prompt-processing time.
    cached_input_tokens: int | None = None
    prompt_ms: int | None = None


def record(result: GenerationResult) -> ModelCall:
    meta = result.metadata
    return ModelCall(
        prompt_version=meta.prompt_version,
        model_id=meta.model_id,
        model_revision=meta.model_revision,
        input_tokens=meta.usage.input_tokens,
        output_tokens=meta.usage.output_tokens,
        first_token_ms=meta.timings.first_token_ms,
        total_ms=meta.timings.total_ms,
        finish_reason=meta.finish_reason,
        cached_input_tokens=meta.timings.cached_input_tokens,
        prompt_ms=meta.timings.prompt_ms,
    )
