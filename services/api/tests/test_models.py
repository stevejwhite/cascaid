import asyncio
import json

import httpx
import pytest

from psychiatry_api.models.contracts import (
    EmbeddingRequest,
    GenerationRequest,
    JsonOutput,
    TextOutput,
)
from psychiatry_api.models.errors import ModelError
from psychiatry_api.models.fakes import FakeEmbeddingModel, FakeLanguageModel
from psychiatry_api.models.local import LocalConfig, LocalEmbeddingModel, LocalLanguageModel
from psychiatry_api.models.runtime import create_runtime


def request(**overrides):
    return GenerationRequest.model_validate(
        {
            "messages": [{"role": "user", "content": "Synthetic question"}],
            "options": {"promptVersion": "test-v1"},
        }
        | overrides
    )


def model(handler, **options):
    config = LocalConfig(
        base_url="http://127.0.0.1:8180/v1", model_id="fixture", revision="1", **options
    )
    return LocalLanguageModel(config, httpx.MockTransport(handler))


def stream(text, finish=True):
    frames = (
        "data: "
        + json.dumps(
            {"choices": [{"delta": {"content": text}, "finish_reason": "stop" if finish else None}]}
        )
        + "\n\n"
    )
    return httpx.Response(200, text=frames + ("data: [DONE]\n\n" if finish else ""))


async def test_local_generation_and_structured_output_preserve_wire_contract():
    result = await model(lambda _: stream('{"answer":"Synthetic"}')).generate(
        request(
            responseFormat={
                "type": "json_schema",
                "name": "answer",
                "schema": {"type": "object", "required": ["answer"]},
            }
        )
    )
    assert result.output.value == {"answer": "Synthetic"}
    assert result.model_dump()["metadata"]["promptVersion"] == "test-v1"
    assert result.metadata.finish_reason == "stop"


async def test_runtime_cache_timings_are_recorded_when_reported():
    timings = {"cache_n": 700, "prompt_n": 120, "prompt_ms": 95.6}
    frames = (
        "data: "
        + json.dumps({"choices": [{"delta": {"content": "Hi"}, "finish_reason": "stop"}]})
        + "\n\ndata: "
        + json.dumps({"choices": [], "timings": timings})
        + "\n\ndata: [DONE]\n\n"
    )
    result = await model(lambda _: httpx.Response(200, text=frames)).generate(request())
    assert result.metadata.timings.cached_input_tokens == 700
    assert result.metadata.timings.processed_input_tokens == 120
    assert result.metadata.timings.prompt_ms == 96
    plain = await model(lambda _: stream("Hi")).generate(request())
    assert plain.metadata.timings.cached_input_tokens is None


@pytest.mark.parametrize(
    "response,code",
    [
        (stream("partial", False), "model_unavailable"),
        (httpx.Response(307, headers={"location": "https://example.invalid"}), "model_unavailable"),
        (httpx.Response(400, text="context exceeded"), "context_overflow"),
        (httpx.Response(429), "resource_exhausted"),
    ],
)
async def test_transport_errors_are_normalized(response, code):
    with pytest.raises(ModelError) as error:
        await model(lambda _: response).generate(request())
    assert error.value.code == code


def test_remote_health_and_endpoints_are_rejected():
    for config in [
        dict(base_url="https://example.invalid"),
        dict(base_url="http://localhost", health_url="https://example.invalid/health"),
    ]:
        with pytest.raises(ModelError) as error:
            LocalLanguageModel(LocalConfig(model_id="fixture", revision="1", **config))
        assert error.value.code == "invalid_request"


class StalledStream(httpx.AsyncByteStream):
    async def __aiter__(self):
        yield b'data: {"choices":[{"delta":{"content":"partial"}}]}\n\n'
        await asyncio.sleep(10)


async def test_whole_request_deadline_includes_stream_body():
    with pytest.raises(ModelError) as error:
        await model(lambda _: httpx.Response(200, stream=StalledStream())).generate(
            request(options={"promptVersion": "test-v1", "timeoutMs": 25})
        )
    assert error.value.code == "model_timeout"


@pytest.mark.parametrize(
    "rows",
    [
        [{"index": 0, "embedding": [1, 0]}, {"index": 0, "embedding": [0, 1]}],
        [{"index": 0, "embedding": [None, 1]}, {"index": 1, "embedding": [1, 0]}],
        [{"index": 0, "embedding": [0, 0]}, {"index": 1, "embedding": [1, 0]}],
    ],
)
async def test_invalid_embedding_vectors_fail(rows):
    adapter = LocalEmbeddingModel(
        LocalConfig(base_url="http://localhost", model_id="fixture", revision="1", dimensions=2),
        httpx.MockTransport(lambda _: httpx.Response(200, json={"data": rows})),
    )
    with pytest.raises(ModelError) as error:
        await adapter.embed(EmbeddingRequest(texts=("first", "second")))
    assert error.value.code == "model_unavailable"


async def test_embedding_order_normalization_and_query_instruction():
    def handler(req):
        assert json.loads(req.content)["input"][0] == "Instruct: Find evidence\nQuery: first"
        return httpx.Response(
            200,
            json={"data": [{"index": 1, "embedding": [0, 2]}, {"index": 0, "embedding": [3, 4]}]},
        )

    adapter = LocalEmbeddingModel(
        LocalConfig(
            base_url="http://localhost",
            model_id="fixture",
            revision="1",
            dimensions=2,
            query_instruction="Find evidence",
            instruction_version="query-v1",
        ),
        httpx.MockTransport(handler),
    )
    result = await adapter.embed(EmbeddingRequest(texts=("first", "second"), task="query"))
    assert result.vectors == ((0.6, 0.8), (0.0, 1.0))


async def test_runtime_capability_gate_and_fake_generation():
    with pytest.raises(ModelError, match="Incompatible"):
        await create_runtime(FakeLanguageModel(), FakeEmbeddingModel(), dimensions=1024)
    runtime = await create_runtime(
        FakeLanguageModel([TextOutput(text="Synthetic")]), FakeEmbeddingModel(), dimensions=8
    )
    assert (await runtime.generate(request())).output.text == "Synthetic"
    with pytest.raises(ModelError):
        await runtime.generate(request())
    fake = FakeLanguageModel([JsonOutput(value={"wrong": True})])
    with pytest.raises(ModelError) as error:
        await fake.generate(
            request(responseFormat={"type": "json_schema", "schema": {"required": ["answer"]}})
        )
    assert error.value.code == "invalid_structured_output"
