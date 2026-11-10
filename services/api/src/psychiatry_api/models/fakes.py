import hashlib
import math
import re

import jsonschema

from psychiatry_api.models.contracts import (
    EmbeddingCapabilities,
    EmbeddingMetadata,
    EmbeddingRequest,
    EmbeddingResult,
    GenerationMetadata,
    GenerationRequest,
    GenerationResult,
    JsonOutput,
    LanguageCapabilities,
    TextDelta,
    TextOutput,
    Timings,
    TokenUsage,
)
from psychiatry_api.models.errors import ModelError
from psychiatry_api.models.local import estimate_tokens


class FakeLanguageModel:
    def __init__(self, outputs: list[TextOutput | JsonOutput] | None = None):
        self.outputs = list(outputs or [])
        self.calls: list[GenerationRequest] = []

    async def capabilities(self) -> LanguageCapabilities:
        return LanguageCapabilities(max_context_tokens=4096)

    async def stream(self, request: GenerationRequest):
        """Yield the configured text word by word, then the result, like a real stream."""
        result = await self.generate(request)
        if isinstance(result.output, TextOutput):
            for word in re.findall(r"\S+\s*", result.output.text):
                yield TextDelta(text=word)
        yield result

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        tokens = estimate_tokens("\n".join(message.content for message in request.messages))
        if tokens + request.options.max_output_tokens > 4096:
            raise ModelError("context_overflow", "Request exceeds fake model context")
        if not self.outputs:
            raise ModelError("model_unavailable", "Fake responses were not configured")
        self.calls.append(request)
        output = self.outputs.pop(0)
        if request.response_format.type == "json_schema":
            if not isinstance(output, JsonOutput):
                raise ModelError("invalid_structured_output", "Expected JSON output")
            try:
                jsonschema.validate(output.value, request.response_format.schema_)
            except jsonschema.ValidationError as error:
                raise ModelError(
                    "invalid_structured_output", "Fake output failed schema"
                ) from error
        output_tokens = estimate_tokens(output.model_dump_json())
        return GenerationResult(
            output=output,
            metadata=GenerationMetadata(
                model_id="fake-language-model",
                model_revision="test-revision",
                runtime="deterministic-fake",
                quantisation="none",
                prompt_version=request.options.prompt_version,
                usage=TokenUsage(
                    input_tokens=tokens,
                    output_tokens=output_tokens,
                    total_tokens=tokens + output_tokens,
                    estimated=True,
                ),
                timings=Timings(first_token_ms=0, total_ms=0),
                finish_reason="stop",
            ),
        )


class FakeEmbeddingModel:
    def __init__(self, dimensions: int = 8):
        self.model_capabilities = EmbeddingCapabilities(
            dimensions=dimensions, max_input_tokens=8192
        )
        self.calls: list[EmbeddingRequest] = []

    async def capabilities(self) -> EmbeddingCapabilities:
        return self.model_capabilities

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        tokens = sum(map(estimate_tokens, request.texts))
        if tokens > self.model_capabilities.max_input_tokens:
            raise ModelError("context_overflow", "Request exceeds fake embedding context")
        self.calls.append(request)
        vectors = []
        for text in request.texts:
            digest = hashlib.sha256(text.encode()).digest()
            values = [
                digest[index % len(digest)] / 127.5 - 1
                for index in range(self.model_capabilities.dimensions)
            ]
            magnitude = math.sqrt(sum(value * value for value in values)) or 1
            vectors.append(tuple(value / magnitude for value in values))
        return EmbeddingResult(
            vectors=tuple(vectors),
            metadata=EmbeddingMetadata(
                model_id="fake-embedding-model",
                model_revision="test-revision",
                runtime="deterministic-fake",
                normalization="l2-v1",
                instruction_version="none-v1",
                input_count=len(request.texts),
                input_tokens=tokens,
                tokens_estimated=True,
                total_ms=0,
            ),
        )
