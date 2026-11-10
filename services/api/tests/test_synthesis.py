import asyncio
import base64
import io
import json
import wave
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from psychiatry_api import health
from psychiatry_api.cases import CASES_PATH, load_case
from psychiatry_api.main import create_app
from psychiatry_api.models.errors import ModelError
from psychiatry_api.roleplay.routes import Presentation, presentation, session_router
from psychiatry_api.synthesis import (
    HeadTtsSynthesizer,
    SynthesisError,
    running_service,
    silent_wav,
    spoken_by_character,
    synthesizer,
)

HEADTTS_REPLY = {
    "words": ["I ", "suppose ", "so."],
    "wtimes": [461.2, 667, 1100],
    "wdurations": [226, 453, 215.4],
    "visemes": ["I", "SS", "PP"],
    "vtimes": [461, 667, 768],
    "vdurations": [174, 70, 72],
    "audio": base64.b64encode(silent_wav(1500)).decode(),
    "audioEncoding": "wav",
}


def test_only_text_the_character_said_counts():
    lines = ["Fine, thanks.  I suppose it started after the divorce, really.", "No."]
    assert spoken_by_character("I suppose it started after the divorce, really.", lines)
    assert spoken_by_character("Fine,\nthanks.", lines)
    assert not spoken_by_character("I have a gun at home.", lines)
    assert not spoken_by_character("   ", lines)


async def test_headtts_synthesizer_posts_to_loopback_and_reads_timings():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=HEADTTS_REPLY)

    tts = HeadTtsSynthesizer(
        "http://127.0.0.1:8183", "kokoro", 5, transport=httpx.MockTransport(handler)
    )
    speech = await tts.synthesize("I suppose so.", "af_bella")
    assert seen["url"] == "http://127.0.0.1:8183/v1/synthesize"
    assert seen["body"] == {
        "input": "I suppose so.",
        "voice": "af_bella",
        "language": "en-us",
        "speed": 1,
        "audioEncoding": "wav",
    }
    assert speech.words == ("I", "suppose", "so.") and speech.word_times == (461, 667, 1100)
    assert speech.word_durations == (226, 453, 215) and speech.visemes == ("I", "SS", "PP")
    assert speech.wav.startswith(b"RIFF") and speech.voice == "af_bella"


async def test_synthesis_failures_and_remote_endpoints_are_rejected():
    for reply in (
        httpx.Response(500),
        httpx.Response(200, json={"error": "Busy"}),
        httpx.Response(200, json={"audio": "not base64!"}),
    ):
        broken = HeadTtsSynthesizer(
            "http://127.0.0.1:8183", "m", 5, transport=httpx.MockTransport(lambda r, x=reply: x)
        )
        with pytest.raises(SynthesisError):
            await broken.synthesize("Hello.", "af_bella")
    with pytest.raises(ModelError):
        HeadTtsSynthesizer("https://tts.example.com", "m", 5)


def test_local_synthesis_needs_an_attested_server_and_an_installed_voice(settings, tmp_path):
    state = tmp_path / "tts-state.json"
    local = settings.model_copy(update={"tts_backend": "local", "tts_state_file": state})
    with pytest.raises(SynthesisError) as error:
        synthesizer(local, "af_bella")
    assert "tts:start" in str(error.value)
    state.write_text(json.dumps({"model": "kokoro", "voices": ["af_bella"]}))
    assert running_service(state) == {"model": "kokoro", "voices": ("af_bella",)}
    assert isinstance(synthesizer(local, "af_bella"), HeadTtsSynthesizer)
    with pytest.raises(SynthesisError) as error:
        synthesizer(local, "am_onyx")
    assert error.value.code == "unknown_voice"
    with pytest.raises(SynthesisError) as error:
        synthesizer(settings, "af_bella")
    assert error.value.code == "disabled"


async def test_voice_readiness_states(settings, tmp_path):
    assert (await health.voice_check(settings)).status == "disabled"
    fake = settings.model_copy(update={"tts_backend": "fake"})
    assert (await health.voice_check(fake)).status == "ready"
    local = settings.model_copy(
        update={"tts_backend": "local", "tts_state_file": tmp_path / "missing.json"}
    )
    check = await health.voice_check(local)
    assert check.status == "unavailable" and "tts:start" in check.detail


@pytest.fixture
def client(settings, tmp_path):
    voiced = settings.model_copy(update={"sessions_path": tmp_path, "tts_backend": "fake"})
    with TestClient(create_app(voiced)) as c:
        yield c


def interview(client) -> tuple[str, str]:
    sid = client.post("/api/sessions", json={"case_id": "elevated-mood-history"}).json()
    begun = client.post(f"/api/sessions/{sid['session_id']}/begin").json()
    return sid["session_id"], begun["transcript"][0]["text"]


def test_character_lines_are_voiced_with_timings_and_not_stored(client, tmp_path):
    sid, opening = interview(client)
    first_sentence = opening.split(". ")[0]
    spoken = client.post(
        f"/api/sessions/{sid}/speech", json={"text": first_sentence, "voice": "af_bella"}
    )
    assert spoken.status_code == 200
    body = spoken.json()
    audio = base64.b64decode(body["audio_wav_base64"])
    with wave.open(io.BytesIO(audio)) as wav:
        assert wav.getframerate() == 24000
    assert body["words"] == first_sentence.split() and body["voice"] == "af_bella"
    assert len(body["word_times_ms"]) == len(body["words"]) == len(body["word_durations_ms"])
    assert "RIFF" not in (tmp_path / f"{sid}.jsonl").read_text()


def test_only_the_characters_own_lines_in_known_voices_can_be_voiced(client, settings, tmp_path):
    sid, opening = interview(client)
    url = f"/api/sessions/{sid}/speech"
    invented = client.post(url, json={"text": "I keep a gun at home.", "voice": "af_bella"})
    assert invented.status_code == 422
    client.post(f"/api/sessions/{sid}/turns", json={"text": "How have you been sleeping?"})
    asked = client.post(url, json={"text": "How have you been sleeping?", "voice": "af_bella"})
    assert asked.status_code == 422  # the candidate's words, not the character's
    assert client.post(url, json={"text": opening, "voice": "../etc"}).status_code == 422
    assert (
        client.post(
            "/api/sessions/unknown/speech", json={"text": "Hi", "voice": "af_bella"}
        ).status_code
        == 404
    )
    off = settings.model_copy(update={"sessions_path": tmp_path})
    with TestClient(create_app(off)) as plain:
        assert plain.post(url, json={"text": opening, "voice": "af_bella"}).status_code == 409
        assert plain.get("/api/status").json()["voice"]["status"] == "disabled"


async def test_synthesis_waits_for_the_generation_slot(settings, tmp_path):
    voiced = settings.model_copy(update={"sessions_path": tmp_path, "tts_backend": "fake"})
    slot = asyncio.Lock()
    app = FastAPI()
    app.include_router(session_router(voiced, slot))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://test") as c:
        sid = (await c.post("/api/sessions", json={"case_id": "elevated-mood-history"})).json()[
            "session_id"
        ]
        opening = (await c.post(f"/api/sessions/{sid}/begin")).json()["transcript"][0]["text"]
        await slot.acquire()  # as if Qwen were generating
        request = asyncio.create_task(
            c.post(f"/api/sessions/{sid}/speech", json={"text": opening, "voice": "af_bella"})
        )
        await asyncio.sleep(0.2)
        assert not request.done()
        slot.release()
        assert (await request).status_code == 200


def test_presentation_follows_the_affect_stage_behind_the_latest_reply():
    case = load_case(CASES_PATH / "overdose-risk-assessment.yaml")
    session = lambda *stages: SimpleNamespace(  # noqa: E731
        case=case, turns=[SimpleNamespace(affect_stage=s) for s in stages]
    )
    assert presentation(session()) == Presentation(expression="flat", hesitations=("Mm.",))
    assert presentation(session("guarded", "opening-up")).expression == "tearful"
    assert presentation(session("opening-up", "defensive")).hesitations == ()


def test_authored_hesitations_can_be_voiced_but_other_fillers_cannot(client):
    sid = client.post("/api/sessions", json={"case_id": "overdose-risk-assessment"}).json()[
        "session_id"
    ]
    begun = client.post(f"/api/sessions/{sid}/begin").json()
    assert begun["presentation"] == {"expression": "flat", "hesitations": ["Mm."]}
    url = f"/api/sessions/{sid}/speech"
    assert (
        client.post(url, json={"text": "Hmmm.", "voice": "af_heart"}).status_code == 200
    )  # a later stage's
    assert client.post(url, json={"text": "Oh.", "voice": "af_heart"}).status_code == 422
