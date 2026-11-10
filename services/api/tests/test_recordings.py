import yaml
from fastapi.testclient import TestClient

from psychiatry_api.main import create_app
from tests.test_speech import wav


def client(settings, tmp_path, enabled=True):
    return TestClient(
        create_app(
            settings.model_copy(update={"recordings_enabled": enabled, "recordings_path": tmp_path})
        )
    )


def post(c, data, speaker="tester-1", item=1, consent="true"):
    return c.post(
        f"/api/recordings?speaker={speaker}&item={item}&consent={consent}",
        content=data,
        headers={"content-type": "audio/wav"},
    )


def test_prompts_are_the_labelled_utterances(settings, tmp_path):
    body = client(settings, tmp_path).get("/api/recordings/prompts").json()
    assert body["enabled"] and len(body["prompts"]) == 95
    assert body["prompts"][0]["item"] == 1 and "consent" in body


def test_recordings_need_opt_in_consent_and_valid_audio(settings, tmp_path):
    with client(settings, tmp_path, enabled=False) as c:
        assert post(c, wav()).status_code == 409
    with client(settings, tmp_path) as c:
        assert post(c, wav(), consent="false").status_code == 409
        assert post(c, wav(), speaker="../etc").status_code == 422
        assert post(c, wav(), item=999).status_code == 422
        assert post(c, wav(rate=44100)).status_code == 422
        saved = post(c, wav(2), item=3).json()
        assert saved == {"item": 3, "recorded": 1, "duration_ms": 2000}
        assert post(c, wav(1), item=3).json()["recorded"] == 1  # re-recording replaces
        prompts = c.get("/api/recordings/prompts").json()["prompts"]
    manifest = yaml.safe_load((tmp_path / "tester-1/manifest.yaml").read_text())["items"]
    assert manifest == [
        {
            "audio": str(tmp_path / "tester-1/003.wav"),
            "reference": prompts[2]["text"],
            "case_id": prompts[2]["case_id"],
            "voice": "tester-1",
        }
    ]
    assert (tmp_path / "tester-1/003.wav").read_bytes()[:4] == b"RIFF"
