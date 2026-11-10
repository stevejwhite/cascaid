import json
import math
from collections.abc import AsyncIterator
from time import perf_counter

import httpx
import jsonschema
from pydantic import Field

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
    WireModel,
)
from psychiatry_api.models.errors import ModelError
from psychiatry_api.models.transport import request_model, validate_endpoint


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


class LocalConfig(WireModel):
    base_url: str
    model_id: str = Field(min_length=1)
    revision: str = Field(min_length=1)
    runtime: str = "unrecorded"
    quantisation: str = "unknown"
    max_context_tokens: int = Field(default=4096, gt=0)
    timeout_ms: int = Field(default=120000, gt=0)
    health_url: str | None = None
    allow_remote: bool = False
    dimensions: int = Field(default=1024, gt=0)
    normalization: str = "l2-v1"
    query_instruction: str | None = None
    instruction_version: str = "none-v1"


class LocalBase:
    def __init__(self, config: LocalConfig, transport: httpx.AsyncBaseTransport | None = None):
        validate_endpoint(config.base_url, config.allow_remote)
        if config.health_url:
            validate_endpoint(config.health_url, config.allow_remote)
        if config.query_instruction and config.instruction_version == "none-v1":
            raise ModelError("invalid_request", "Query instructions require a version")
        self.config, self.transport = config, transport

    def request(self, url: str, payload: dict | None = None, timeout_ms: int | None = None):
        return request_model(
            url,
            payload=payload,
            timeout_ms=timeout_ms or self.config.timeout_ms,
            allow_remote=self.config.allow_remote,
            transport=self.transport,
        )

    async def health(self) -> None:
        url = self.config.health_url or str(
            httpx.URL(self.config.base_url).copy_with(path="/health")
        )
        async with self.request(url, timeout_ms=min(5000, self.config.timeout_ms)) as response:
            await response.aread()


class LocalLanguageModel(LocalBase):
    async def capabilities(self) -> LanguageCapabilities:
        await self.health()
        return LanguageCapabilities(max_context_tokens=self.config.max_context_tokens)

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        result = None
        async for event in self.stream(request):
            if isinstance(event, GenerationResult):
                result = event
        assert result is not None
        return result

    async def stream(
        self, request: GenerationRequest
    ) -> AsyncIterator[TextDelta | GenerationResult]:
        """Yield text as it is generated, then the complete GenerationResult."""
        payload = {
            "model": self.config.model_id,
            "messages": [message.model_dump() for message in request.messages],
            "temperature": request.options.temperature,
            "max_tokens": request.options.max_output_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if request.options.seed is not None:
            payload["seed"] = request.options.seed
        if request.response_format.type == "json_schema":
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": request.response_format.name,
                    "schema": request.response_format.schema_,
                    "strict": True,
                },
            }
        started = perf_counter()
        text, usage, finish_reason, first_token, done = "", {}, None, None, False
        runtime_timings: dict = {}
        async with self.request(
            f"{self.config.base_url.rstrip('/')}/chat/completions",
            payload,
            request.options.timeout_ms,
        ) as response:
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                value = line[5:].strip()
                if not value:
                    continue
                if value == "[DONE]":
                    done = True
                    break
                event = json.loads(value)
                if event.get("error"):
                    raise ModelError("model_unavailable", "Runtime reported a streaming error")
                choice = (event.get("choices") or [{}])[0]
                content = (choice.get("delta") or {}).get("content") or ""
                if not isinstance(content, str):
                    raise ModelError("model_unavailable", "Invalid streaming content")
                if content and first_token is None:
                    first_token = round((perf_counter() - started) * 1000)
                text += content
                if content:
                    yield TextDelta(text=content)
                finish_reason = choice.get("finish_reason") or finish_reason
                usage = event.get("usage") or usage
                runtime_timings = event.get("timings") or runtime_timings
        if not done or not isinstance(finish_reason, str) or not finish_reason:
            raise ModelError("model_unavailable", "Incomplete completion stream")
        if request.response_format.type == "json_schema":
            try:
                value = json.loads(text)
                jsonschema.validate(value, request.response_format.schema_)
            except (ValueError, jsonschema.ValidationError, jsonschema.SchemaError) as error:
                raise ModelError(
                    "invalid_structured_output", "Output failed schema validation"
                ) from error
            output = JsonOutput(value=value)
        else:
            output = TextOutput(text=text)
        input_tokens = usage.get(
            "prompt_tokens", estimate_tokens("\n".join(m.content for m in request.messages))
        )
        output_tokens = usage.get("completion_tokens", estimate_tokens(text))
        yield GenerationResult(
            output=output,
            metadata=GenerationMetadata(
                model_id=self.config.model_id,
                model_revision=self.config.revision,
                runtime=self.config.runtime,
                quantisation=self.config.quantisation,
                prompt_version=request.options.prompt_version,
                usage=TokenUsage(
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=usage.get("total_tokens", input_tokens + output_tokens),
                    estimated="prompt_tokens" not in usage,
                ),
                timings=Timings(
                    first_token_ms=first_token,
                    total_ms=round((perf_counter() - started) * 1000),
                    cached_input_tokens=runtime_timings.get("cache_n"),
                    processed_input_tokens=runtime_timings.get("prompt_n"),
                    prompt_ms=(
                        round(runtime_timings["prompt_ms"])
                        if isinstance(runtime_timings.get("prompt_ms"), int | float)
                        else None
                    ),
                ),
                finish_reason=finish_reason,
            ),
        )


class LocalEmbeddingModel(LocalBase):
    async def capabilities(self) -> EmbeddingCapabilities:
        await self.health()
        return EmbeddingCapabilities(
            dimensions=self.config.dimensions, max_input_tokens=self.config.max_context_tokens
        )

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        texts = list(request.texts)
        if request.task == "query" and self.config.query_instruction:
            texts = [f"Instruct: {self.config.query_instruction}\nQuery: {text}" for text in texts]
        started = perf_counter()
        async with self.request(
            f"{self.config.base_url.rstrip('/')}/embeddings",
            {
                "model": self.config.model_id,
                "input": texts,
                "encoding_format": "float",
            },
        ) as response:
            body = json.loads(await response.aread())
            rows = body.get("data")
            if not isinstance(rows, list) or len(rows) != len(texts):
                raise ModelError("model_unavailable", "Invalid embedding count")
            vectors = {}
            for row in rows:
                index, vector = row.get("index"), row.get("embedding")
                if type(index) is not int or not 0 <= index < len(texts) or index in vectors:
                    raise ModelError("model_unavailable", "Invalid embedding indices")
                if (
                    not isinstance(vector, list)
                    or len(vector) != self.config.dimensions
                    or any(
                        type(value) not in (float, int) or not math.isfinite(value)
                        for value in vector
                    )
                ):
                    raise ModelError("model_unavailable", "Invalid embedding coordinates")
                magnitude = math.hypot(*vector)
                if not math.isfinite(magnitude) or magnitude == 0:
                    raise ModelError("model_unavailable", "Invalid embedding magnitude")
                vectors[index] = (
                    tuple(value / magnitude for value in vector)
                    if self.config.normalization == "l2-v1"
                    else tuple(vector)
                )
        return EmbeddingResult(
            vectors=tuple(vectors[index] for index in range(len(texts))),
            metadata=EmbeddingMetadata(
                model_id=self.config.model_id,
                model_revision=self.config.revision,
                runtime=self.config.runtime,
                normalization=self.config.normalization,
                instruction_version=self.config.instruction_version,
                input_count=len(texts),
                input_tokens=body.get("usage", {}).get(
                    "prompt_tokens", sum(map(estimate_tokens, texts))
                ),
                tokens_estimated="prompt_tokens" not in body.get("usage", {}),
                total_ms=round((perf_counter() - started) * 1000),
            ),
        )
