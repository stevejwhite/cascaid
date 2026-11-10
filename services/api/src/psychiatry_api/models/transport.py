import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

import httpx

from psychiatry_api.models.errors import ModelError, normalize_error


def validate_endpoint(url: str, allow_remote: bool = False) -> None:
    parsed = urlsplit(url)
    if type(allow_remote) is not bool:
        raise ModelError("invalid_request", "allowRemote must be a boolean")
    if parsed.scheme not in {"http", "https"} or parsed.username or parsed.password:
        raise ModelError("invalid_request", "Model endpoints require HTTP(S) without credentials")
    if not allow_remote and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ModelError("invalid_request", "Local adapters require a loopback URL")


@asynccontextmanager
async def request_model(
    url: str,
    *,
    timeout_ms: int,
    payload: dict | None = None,
    allow_remote: bool = False,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AsyncIterator[httpx.Response]:
    validate_endpoint(url, allow_remote)
    if timeout_ms <= 0:
        raise ModelError("invalid_request", "A positive timeout is required")
    try:
        # HTTPX per-read timeouts alone do not bound a slowly progressing stream.
        async with (
            asyncio.timeout(timeout_ms / 1000),
            httpx.AsyncClient(
                timeout=timeout_ms / 1000,
                follow_redirects=False,
                trust_env=False,
                transport=transport,
            ) as client,
            client.stream("POST" if payload is not None else "GET", url, json=payload) as response,
        ):
            if not response.is_success:
                body = (await response.aread()).decode(errors="replace").lower()
                status = response.status_code
                if status in {408, 504}:
                    code = "model_timeout"
                elif status == 413 or "context" in body or "too many tokens" in body:
                    code = "context_overflow"
                elif status == 429 or "out of memory" in body or "resource exhausted" in body:
                    code = "resource_exhausted"
                elif 400 <= status < 500:
                    code = "invalid_request"
                else:
                    code = "model_unavailable"
                raise ModelError(code, "Model endpoint rejected the request")
            yield response
    except (TimeoutError, httpx.TimeoutException) as error:
        raise ModelError("model_timeout", "Model request timed out") from error
    except Exception as error:
        raise normalize_error(error) from error
