"""The fine-tuned student interpreter, served locally by mlx_lm.server (npm run student:start).

It answers one short JSON object per line (psychiatry_api.finetune.format); this adapter
only sends the prompt and returns the text. Loopback only; no hosted fallback.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import httpx

from psychiatry_api.models.errors import ModelError
from psychiatry_api.models.transport import validate_endpoint


@dataclass(frozen=True)
class StudentReply:
    text: str
    total_ms: int
    input_tokens: int | None
    output_tokens: int | None
    cached_input_tokens: int | None


def running_student(state_file: Path) -> dict | None:
    """What npm run student:start attested it is serving (model, format, weights checksum)."""
    try:
        state = json.loads(state_file.read_text())
        return {k: state[k] for k in ("model", "format_version", "weights_sha256")}
    except (OSError, ValueError, KeyError, TypeError):
        return None


class StudentModel:
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

    async def complete(self, system: str, user: str) -> StudentReply:
        body = {
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
            "max_tokens": 160,
            # As in training: the empty think block is part of the prompt.
            "chat_template_kwargs": {"enable_thinking": False},
        }
        started = perf_counter()
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=self.timeout_s, trust_env=False
            ) as client:
                response = await client.post(
                    f"{self.base_url.rstrip('/')}/v1/chat/completions", json=body
                )
                response.raise_for_status()
                data = response.json()
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as error:
            raise ModelError("model_unavailable", "The student interpreter failed") from error
        details = usage.get("prompt_tokens_details") or {}
        return StudentReply(
            text=text,
            total_ms=round((perf_counter() - started) * 1000),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            cached_input_tokens=details.get("cached_tokens"),
        )
