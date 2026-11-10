import asyncio
from dataclasses import dataclass

from psychiatry_api.models.contracts import (
    EmbeddingModel,
    EmbeddingRequest,
    EmbeddingResult,
    GenerationRequest,
    GenerationResult,
    LanguageModel,
)
from psychiatry_api.models.errors import ModelError, normalize_error


@dataclass(frozen=True)
class ModelRuntime:
    language: LanguageModel
    embedding: EmbeddingModel

    async def generate(self, request: GenerationRequest) -> GenerationResult:
        try:
            return await self.language.generate(request)
        except Exception as error:
            raise normalize_error(error) from error

    async def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        try:
            return await self.embedding.embed(request)
        except Exception as error:
            raise normalize_error(error) from error


async def create_runtime(
    language: LanguageModel,
    embedding: EmbeddingModel,
    *,
    minimum_context_tokens: int = 4096,
    dimensions: int = 1024,
) -> ModelRuntime:
    try:
        language_capabilities, embedding_capabilities = await asyncio.gather(
            language.capabilities(), embedding.capabilities()
        )
        if not (language_capabilities.text_generation and language_capabilities.structured_output):
            raise ModelError("unsupported_capability", "Text and structured output are required")
        if language_capabilities.max_context_tokens < minimum_context_tokens:
            raise ModelError("unsupported_capability", "Insufficient model context")
        if (
            not embedding_capabilities.batch_embedding
            or embedding_capabilities.dimensions != dimensions
        ):
            raise ModelError("unsupported_capability", "Incompatible embedding capabilities")
        return ModelRuntime(language, embedding)
    except Exception as error:
        raise normalize_error(error) from error
