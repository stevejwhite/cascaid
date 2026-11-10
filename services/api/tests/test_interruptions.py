import json

import pytest
from fastapi.testclient import TestClient

from psychiatry_api.main import create_app


@pytest.fixture
def client(settings, tmp_path):
    with TestClient(create_app(settings.model_copy(update={"sessions_path": tmp_path}))) as c:
        yield c


def test_interruptions_are_logged_and_counted_in_feedback(client, tmp_path):
    sid = client.post("/api/sessions", json={"case_id": "alcohol-history"}).json()["session_id"]
    url = f"/api/sessions/{sid}/interruptions"
    assert client.post(url, json={"during": "speaking", "heard_ms": 800}).status_code == 409
    client.post(f"/api/sessions/{sid}/begin")
    assert client.post(url, json={"during": "speaking", "heard_ms": 1200}).status_code == 204
    client.post(f"/api/sessions/{sid}/turns", json={"text": "How much do you drink?"})
    assert client.post(url, json={"during": "thinking", "heard_ms": 0}).status_code == 204

    rows = [json.loads(line) for line in (tmp_path / f"{sid}.jsonl").read_text().splitlines()]
    cut = [
        (r["after_turn"], r["during"], r["heard_ms"]) for r in rows if r["type"] == "interrupted"
    ]
    assert cut == [(0, "speaking", 1200), (1, "thinking", 0)]
    debrief = client.post(f"/api/sessions/{sid}/end").json()
    assert debrief["feedback"]["communication"]["interruptions"] == 2
    # The transcript is unchanged: an interruption removes nothing the character said.
    assert len(debrief["session"]["transcript"]) == 3
    assert client.post(url, json={"during": "speaking", "heard_ms": 1}).status_code == 409


def test_interruption_requests_are_validated(client):
    sid = client.post("/api/sessions", json={"case_id": "alcohol-history"}).json()["session_id"]
    client.post(f"/api/sessions/{sid}/begin")
    url = f"/api/sessions/{sid}/interruptions"
    assert client.post(url, json={"during": "listening", "heard_ms": 0}).status_code == 422
    assert client.post(url, json={"during": "speaking", "heard_ms": -5}).status_code == 422
    assert (
        client.post(
            "/api/sessions/unknown/interruptions", json={"during": "speaking", "heard_ms": 0}
        ).status_code
        == 404
    )
