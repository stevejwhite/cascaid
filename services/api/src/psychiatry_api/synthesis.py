"""Local speech synthesis for the character's voice, behind a provider-neutral interface.

Only sentences the character has already said in the session are synthesised (the reply
has passed the disclosure gates and the output guard before it reaches here). Audio is
returned to the browser and never written to disk.
"""

import base64
import io
import json
import re
import wave
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Protocol

import httpx

from psychiatry_api.config import Settings
from psychiatry_api.models.transport import validate_endpoint

MAX_CHARACTERS = 600


class SynthesisError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Speech:
    """WAV audio with word and viseme timings in milliseconds from the start of the audio."""

    wav: bytes
    words: tuple[str, ...]
    word_times: tuple[int, ...]
    word_durations: tuple[int, ...]
    visemes: tuple[str, ...]
    viseme_times: tuple[int, ...]
    viseme_durations: tuple[int, ...]
    voice: str
    model: str
    synthesis_ms: int


def normalised(text: str) -> str:
    return " ".join(text.split())


def spoken_by_character(text: str, lines: list[str]) -> bool:
    """Whether text is all or part of something the character said (a released sentence)."""
    wanted = normalised(text)
    return bool(wanted) and any(wanted in normalised(line) for line in lines)


class Synthesizer(Protocol):
    id: str

    async def synthesize(self, text: str, voice: str) -> Speech: ...


def silent_wav(milliseconds: int, rate: int = 24000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"\0\0" * (rate * milliseconds // 1000))
    return buffer.getvalue()


class FakeSynthesizer:
    """Deterministic stand-in for development and tests: silence with evenly spaced words."""

    id = "fake-tts"

    async def synthesize(self, text, voice):
        words = tuple(re.findall(r"\S+", text))
        times = tuple(100 + 300 * i for i in range(len(words)))
        return Speech(
            wav=silent_wav(200 + 300 * len(words)),
            words=words,
            word_times=times,
            word_durations=(280,) * len(words),
            visemes=("aa",) * len(words),
            viseme_times=times,
            viseme_durations=(200,) * len(words),
            voice=voice,
            model=self.id,
            synthesis_ms=0,
        )


def integers(values) -> tuple[int, ...]:
    return tuple(round(v) for v in values)


class HeadTtsSynthesizer:
    """The pinned HeadTTS server (Kokoro-82M) on loopback, started by npm run tts:start."""

    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_s: float,
        language: str = "en-us",
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        validate_endpoint(base_url)
        self.base_url, self.model, self.timeout_s = base_url, model, timeout_s
        self.language, self.transport = language, transport
        self.id = f"headtts:{model}"

    async def synthesize(self, text, voice):
        body = {
            "input": text,
            "voice": voice,
            "language": self.language,
            "speed": 1,
            "audioEncoding": "wav",
        }
        started = perf_counter()
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=self.timeout_s, trust_env=False
            ) as client:
                response = await client.post(
                    f"{self.base_url.rstrip('/')}/v1/synthesize", json=body
                )
                response.raise_for_status()
                data = response.json()
            if "error" in data:
                raise ValueError(data["error"])
            return Speech(
                wav=base64.b64decode(data["audio"], validate=True),
                words=tuple(w.strip() for w in data["words"]),
                word_times=integers(data["wtimes"]),
                word_durations=integers(data["wdurations"]),
                visemes=tuple(data["visemes"]),
                viseme_times=integers(data["vtimes"]),
                viseme_durations=integers(data["vdurations"]),
                voice=voice,
                model=self.model,
                synthesis_ms=round((perf_counter() - started) * 1000),
            )
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
            raise SynthesisError("tts_unavailable", "Local speech synthesis failed") from error


def running_service(state_file: Path) -> dict | None:
    """What the managed server was started with, as attested by tts:start."""
    try:
        state = json.loads(state_file.read_text())
        return {"model": state["model"], "voices": tuple(state["voices"])}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def synthesizer(settings: Settings, voice: str) -> Synthesizer:
    if settings.tts_backend == "fake":
        return FakeSynthesizer()
    if settings.tts_backend != "local":
        raise SynthesisError("disabled", "The character's voice is turned off")
    service = running_service(settings.tts_state_file)
    if service is None:
        raise SynthesisError(
            "tts_unavailable", "Start local speech synthesis with npm run tts:start"
        )
    if voice not in service["voices"]:
        raise SynthesisError("unknown_voice", "That voice is not installed")
    return HeadTtsSynthesizer(
        settings.tts_base_url, service["model"], settings.model_timeout_seconds
    )
