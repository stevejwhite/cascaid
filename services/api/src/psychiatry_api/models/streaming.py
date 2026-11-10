"""Stream text from any LanguageModel; models without streaming yield their whole output."""

from collections.abc import AsyncIterator

from psychiatry_api.models.contracts import (
    GenerationRequest,
    GenerationResult,
    LanguageModel,
    TextDelta,
    TextOutput,
)


async def stream_text(
    model: LanguageModel, request: GenerationRequest
) -> AsyncIterator[TextDelta | GenerationResult]:
    if hasattr(model, "stream"):
        async for event in model.stream(request):
            yield event
        return
    result = await model.generate(request)
    if isinstance(result.output, TextOutput):
        yield TextDelta(text=result.output.text)
    yield result
