import io
import json
import math
import struct
import wave

import httpx
import pytest
from fastapi.testclient import TestClient

from psychiatry_api import health
from psychiatry_api.main import create_app
from psychiatry_api.models.errors import ModelError
from psychiatry_api.speech import (
    MAX_SECONDS,
    SpeechError,
    WhisperCppRecognizer,
    clean,
    recognizer,
    running_model,
    validate_wav,
)


def wav(seconds=1.0, rate=16000, channels=1, width=2) -> bytes:
    frames = int(seconds * rate)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(width)
        out.setframerate(rate)
        tone = (int(3000 * math.sin(i / 8)) for i in range(frames * channels))
        if width == 2:
            out.writeframes(b"".join(struct.pack("<h", sample) for sample in tone))
        else:
            out.writeframes(bytes(frames * channels * width))
    return buffer.getvalue()


def test_only_short_16khz_mono_pcm_wav_is_accepted():
    assert validate_wav(wav(1.5)).duration_ms == 1500
    for bad, code in [
        (wav(rate=44100), "invalid_audio"),
        (wav(channels=2), "invalid_audio"),
        (wav(width=1), "invalid_audio"),
        (b"not audio at all", "invalid_audio"),
        (wav(0.1), "too_short"),
        (wav(MAX_SECONDS + 1), "too_long"),
    ]:
        with pytest.raises(SpeechError) as error:
            validate_wav(bad)
        assert error.value.code == code


def test_whisper_annotations_are_removed():
    assert clean(" [BLANK_AUDIO] ") == ""
    assert clean(" (coughs) How are you  sleeping? *sighs*\n") == "How are you sleeping?"


async def test_whisper_cpp_recognizer_posts_wav_and_prompt_to_loopback():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.content
        return httpx.Response(200, json={"text": " Have you had a fit? [BLANK_AUDIO]\n"})

    asr = WhisperCppRecognizer(
        "http://127.0.0.1:8182", "ggml-test.bin", 5, httpx.MockTransport(handler)
    )
    result = await asr.transcribe(validate_wav(wav()), "A psychiatry interview with Chris.")
    assert result.text == "Have you had a fit?" and result.model == "ggml-test.bin"
    assert result.raw_text == "Have you had a fit? [BLANK_AUDIO]"
    assert seen["url"] == "http://127.0.0.1:8182/inference"
    assert b"A psychiatry interview with Chris." in seen["body"] and b"RIFF" in seen["body"]


async def test_recognizer_failures_and_remote_endpoints_are_rejected():
    broken = WhisperCppRecognizer(
        "http://127.0.0.1:8182", "m", 5, httpx.MockTransport(lambda r: httpx.Response(500))
    )
    with pytest.raises(SpeechError):
        await broken.transcribe(validate_wav(wav()))
    with pytest.raises(ModelError, match="loopback"):
        WhisperCppRecognizer("https://speech.example.com", "m", 5)


def test_local_recognizer_needs_an_attested_running_server(settings, tmp_path):
    state = tmp_path / "speech-state.json"
    local = settings.model_copy(update={"speech_backend": "local", "speech_state_file": state})
    with pytest.raises(SpeechError, match="speech:start"):
        recognizer(local)
    state.write_text(json.dumps({"model": "ggml-large-v3-turbo-q5_0.bin"}))
    assert running_model(state) == "ggml-large-v3-turbo-q5_0.bin"
    assert recognizer(local).id == "whisper.cpp:ggml-large-v3-turbo-q5_0.bin"
    with pytest.raises(SpeechError, match="off"):
        recognizer(settings.model_copy(update={"speech_backend": "off"}))


async def test_speech_readiness_states(settings, tmp_path):
    assert (await health.speech_check(settings)).status == "disabled"
    fake = settings.model_copy(update={"speech_backend": "fake"})
    assert (await health.speech_check(fake)).status == "ready"
    local = settings.model_copy(
        update={"speech_backend": "local", "speech_state_file": tmp_path / "missing.json"}
    )
    check = await health.speech_check(local)
    assert check.status == "unavailable" and "speech:start" in check.detail


@pytest.fixture
def client(settings, tmp_path):
    speaking = settings.model_copy(update={"sessions_path": tmp_path, "speech_backend": "fake"})
    with TestClient(create_app(speaking)) as c:
        yield c


def interview(client) -> str:
    sid = client.post("/api/sessions", json={"case_id": "elevated-mood-history"}).json()
    client.post(f"/api/sessions/{sid['session_id']}/begin")
    return sid["session_id"]


def post_audio(client, sid, data):
    return client.post(
        f"/api/sessions/{sid}/transcriptions", content=data, headers={"content-type": "audio/wav"}
    )


def test_spoken_turns_are_logged_without_audio(client, tmp_path):
    sid = client.post("/api/sessions", json={"case_id": "elevated-mood-history"}).json()
    assert post_audio(client, sid["session_id"], wav()).status_code == 409  # still reading
    sid = interview(client)
    heard = post_audio(client, sid, wav(2)).json()
    assert heard["text"] == "How have you been sleeping recently?" and heard["audio_ms"] == 2000

    turn = client.post(
        f"/api/sessions/{sid}/turns",
        json={"text": heard["text"], "transcription_id": heard["transcription_id"]},
    )
    assert "three hours a night" in turn.json()["transcript"][-1]["text"]
    reused = client.post(
        f"/api/sessions/{sid}/turns",
        json={"text": "Again", "transcription_id": heard["transcription_id"]},
    )
    assert reused.status_code == 409
    second = post_audio(client, sid, wav()).json()
    client.post(
        f"/api/sessions/{sid}/turns",
        json={"text": "How is your mood?", "transcription_id": second["transcription_id"]},
    )
    client.post(f"/api/sessions/{sid}/turns", json={"text": "Any alcohol?"})

    log = (tmp_path / f"{sid}.jsonl").read_text()
    rows = [json.loads(line) for line in log.splitlines()]
    heard_rows = [r for r in rows if r["type"] == "transcribed"]
    assert len(heard_rows) == 2 and heard_rows[0]["recognizer"] == "fake-asr"
    assert heard_rows[0]["prompt"] == "A psychiatry interview with Alex."
    turns = [r for r in rows if r["type"] == "turn"]
    assert [(t["input"], t["edited"]) for t in turns] == [
        ("speech", False),
        ("speech", True),
        ("typed", None),
    ]
    assert "RIFF" not in log


def test_bad_or_disabled_audio_requests_are_refused(client, settings, tmp_path):
    sid = interview(client)
    assert post_audio(client, sid, wav(rate=44100)).status_code == 422
    assert post_audio(client, sid, wav(MAX_SECONDS + 2)).status_code == 413
    unknown = client.post(
        f"/api/sessions/{sid}/turns", json={"text": "Hi", "transcription_id": "f" * 32}
    )
    assert unknown.status_code == 409
    off = settings.model_copy(update={"sessions_path": tmp_path})
    with TestClient(create_app(off)) as plain:
        assert post_audio(plain, sid, wav()).status_code == 409
        assert plain.get("/api/status").json()["speech"]["status"] == "disabled"
