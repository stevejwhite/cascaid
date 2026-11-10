from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class WireModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        serialize_by_alias=True,
        extra="forbid",
        frozen=True,
    )


class Message(WireModel):
    role: Literal["system", "user", "assistant"]
    content: str


class GenerationOptions(WireModel):
    prompt_version: str = Field(min_length=1)
    max_output_tokens: int = Field(default=256, gt=0)
    temperature: float = Field(default=0, ge=0, le=2)
    seed: int | None = None
    timeout_ms: int = Field(default=120000, gt=0)


class ResponseFormat(WireModel):
    type: Literal["text", "json_schema"] = "text"
    name: str = "answer"
    schema_: dict[str, Any] = Field(default_factory=dict, alias="schema")


class GenerationRequest(WireModel):
    messages: tuple[Message, ...] = Field(min_length=1)
    options: GenerationOptions
    response_format: ResponseFormat = Field(default_factory=ResponseFormat)


class TextOutput(WireModel):
    type: Literal["text"] = "text"
    text: str


class JsonOutput(WireModel):
    type: Literal["json"] = "json"
    value: Any


class TokenUsage(WireModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated: bool


class Timings(WireModel):
    first_token_ms: int | None
    total_ms: int
    # Reported by the runtime when available: prompt tokens reused from its cache, prompt
    # tokens processed afresh, and the time spent processing them.
    cached_input_tokens: int | None = None
    processed_input_tokens: int | None = None
    prompt_ms: int | None = None


class GenerationMetadata(WireModel):
    model_id: str
    model_revision: str
    runtime: str
    quantisation: str
    prompt_version: str
    usage: TokenUsage
    timings: Timings
    finish_reason: str


class TextDelta(WireModel):
    """A piece of generated text, streamed before the final GenerationResult."""

    type: Literal["delta"] = "delta"
    text: str


class GenerationResult(WireModel):
    output: TextOutput | JsonOutput = Field(discriminator="type")
    metadata: GenerationMetadata


class EmbeddingRequest(WireModel):
    texts: tuple[str, ...] = Field(min_length=1)
    task: Literal["query", "document", "classification"] | None = None


class EmbeddingMetadata(WireModel):
    model_id: str
    model_revision: str
    runtime: str
    normalization: str
    instruction_version: str
    input_count: int
    input_tokens: int
    tokens_estimated: bool
    total_ms: int


class EmbeddingResult(WireModel):
    vectors: tuple[tuple[float, ...], ...]
    metadata: EmbeddingMetadata


class LanguageCapabilities(WireModel):
    text_generation: bool = True
    structured_output: bool = True
    streaming: bool = True
    max_context_tokens: int = Field(default=4096, gt=0)


class EmbeddingCapabilities(WireModel):
    batch_embedding: bool = True
    dimensions: int = Field(gt=0)
    max_input_tokens: int = Field(default=4096, gt=0)


class LanguageModel(Protocol):
    async def capabilities(self) -> LanguageCapabilities: ...
    async def generate(self, request: GenerationRequest) -> GenerationResult: ...


class EmbeddingModel(Protocol):
    async def capabilities(self) -> EmbeddingCapabilities: ...
    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult: ...
