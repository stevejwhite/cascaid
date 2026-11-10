"""The topic reranker, served locally with MLX (npm run reranker:start; docs/RERANKER-PLAN.md).

It scores a query against several documents and returns one probability per document; this
adapter only sends the texts and returns the scores. Loopback only; no hosted fallback.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import httpx

from psychiatry_api.models.errors import ModelError
from psychiatry_api.models.transport import validate_endpoint


@dataclass(frozen=True)
class RerankReply:
    scores: tuple[float, ...]
    total_ms: int


def running_reranker(state_file: Path) -> dict | None:
    """What npm run reranker:start attested it is serving (model, revision, weights checksum)."""
    try:
        state = json.loads(state_file.read_text())
        return {k: state[k] for k in ("model", "revision", "weights_sha256")}
    except (OSError, ValueError, KeyError, TypeError):
        return None


class RerankerModel:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_s: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        validate_endpoint(base_url)
        self.base_url, self.model, self.timeout_s, self.transport = (
            base_url,
            model,
            timeout_s,
            transport,
        )

    async def score(self, instruction: str, query: str, documents: list[str]) -> RerankReply:
        body = {"instruction": instruction, "query": query, "documents": documents}
        started = perf_counter()
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=self.timeout_s, trust_env=False
            ) as client:
                response = await client.post(f"{self.base_url.rstrip('/')}/v1/rerank", json=body)
                response.raise_for_status()
                scores = tuple(float(s) for s in response.json()["scores"])
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise ModelError("model_unavailable", "The topic reranker failed") from error
        if len(scores) != len(documents):
            raise ModelError(
                "invalid_structured_output", "The topic reranker returned the wrong count"
            )
        return RerankReply(scores=scores, total_ms=round((perf_counter() - started) * 1000))
