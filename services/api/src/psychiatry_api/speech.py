"""Local speech recognition behind a provider-neutral interface.

Audio is held in memory for one request, sent only to the loopback whisper.cpp server and
never written to disk; session logs keep the transcript and timings, not the audio.
"""

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

SAMPLE_RATE = 16000
MIN_SECONDS, MAX_SECONDS = 0.3, 60
# 16-bit mono at 16 kHz for the maximum duration, plus a generous header allowance.
MAX_BYTES = MAX_SECONDS * SAMPLE_RATE * 2 + 4096


class SpeechError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Audio:
    data: bytes
    duration_ms: int


@dataclass(frozen=True)
class Transcription:
    text: str
    raw_text: str
    model: str
    asr_ms: int


def validate_wav(data: bytes) -> Audio:
    """Accept only 16 kHz mono 16-bit PCM WAV, the format the browser recorder produces."""
    if len(data) > MAX_BYTES:
        raise SpeechError("too_long", f"Recordings are limited to {MAX_SECONDS} seconds")
    try:
        with wave.open(io.BytesIO(data)) as audio:
            rate, channels, width = audio.getframerate(), audio.getnchannels(), audio.getsampwidth()
            frames = audio.getnframes()
    except (wave.Error, EOFError) as error:
        raise SpeechError("invalid_audio", "Audio must be a WAV file") from error
    if (rate, channels, width) != (SAMPLE_RATE, 1, 2):
        raise SpeechError("invalid_audio", "Audio must be 16 kHz mono 16-bit PCM")
    seconds = frames / rate
    if seconds < MIN_SECONDS:
        raise SpeechError("too_short", "The recording was too short")
    if seconds > MAX_SECONDS:
        raise SpeechError("too_long", f"Recordings are limited to {MAX_SECONDS} seconds")
    return Audio(data=data, duration_ms=round(seconds * 1000))


def clean(text: str) -> str:
    """Drop Whisper's non-speech annotations such as [BLANK_AUDIO] or (coughs)."""
    text = re.sub(r"\[[^\]]*\]|\([^)]*\)|\*[^*]*\*", " ", text)
    return " ".join(text.split())


def vocabulary_prompt(character: str) -> str:
    # Deliberately minimal: naming the character fixes its spelling without biasing the
    # recogniser towards case topics the candidate has not mentioned.
    return f"A psychiatry interview with {character}."


class Recognizer(Protocol):
    id: str

    async def transcribe(self, audio: Audio, prompt: str | None = None) -> Transcription: ...


class FakeRecognizer:
    """Deterministic stand-in for development and tests; it ignores the audio content."""

    id = "fake-asr"

    def __init__(self, text: str = "How have you been sleeping recently?"):
        self.text = text

    async def transcribe(self, audio, prompt=None):
        return Transcription(text=self.text, raw_text=self.text, model=self.id, asr_ms=0)


class WhisperCppRecognizer:
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
        self.id = f"whisper.cpp:{model}"

    async def transcribe(self, audio, prompt=None):
        fields = {"response_format": "json", "temperature": "0"}
        if prompt:
            fields["prompt"] = prompt
        started = perf_counter()
        try:
            async with httpx.AsyncClient(
                transport=self.transport, timeout=self.timeout_s, trust_env=False
            ) as client:
                response = await client.post(
                    f"{self.base_url.rstrip('/')}/inference",
                    data=fields,
                    files={"file": ("speech.wav", audio.data, "audio/wav")},
                )
                response.raise_for_status()
                raw = response.json().get("text")
        except (httpx.HTTPError, ValueError) as error:
            raise SpeechError("asr_unavailable", "Local speech recognition failed") from error
        if not isinstance(raw, str):
            raise SpeechError("asr_unavailable", "Local speech recognition returned no text")
        return Transcription(
            text=clean(raw),
            raw_text=raw.strip(),
            model=self.model,
            asr_ms=round((perf_counter() - started) * 1000),
        )


def running_model(state_file: Path) -> str | None:
    """The model the managed server was started with, as attested by speech:start."""
    try:
        return json.loads(state_file.read_text())["model"]
    except (OSError, ValueError, KeyError):
        return None


def recognizer(settings: Settings) -> Recognizer:
    if settings.speech_backend == "fake":
        return FakeRecognizer()
    if settings.speech_backend != "local":
        raise SpeechError("disabled", "Speech input is turned off")
    model = running_model(settings.speech_state_file)
    if model is None:
        raise SpeechError(
            "asr_unavailable", "Start local speech recognition with npm run speech:start"
        )
    return WhisperCppRecognizer(settings.asr_base_url, model, settings.model_timeout_seconds)
