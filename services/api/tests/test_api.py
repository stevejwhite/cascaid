from fastapi.testclient import TestClient

from psychiatry_api import health
from psychiatry_api.main import create_app
from psychiatry_api.schemas import ServiceCheck


async def healthy(*args):
    return ServiceCheck(status="ready", detail="Test model")


async def unavailable(*args):
    return ServiceCheck(status="unavailable", detail="Test model")


def test_fake_backend_is_ready_without_a_model_server(settings, monkeypatch):
    monkeypatch.setattr(health, "model_check", unavailable)
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").json()["status"] == "ok"
        response = client.get("/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["model_backend"] == "fake"
        assert body["cases"]["status"] == body["registry"]["status"] == "ready"
        assert body["generation"]["status"] == "unavailable"


def test_local_backend_requires_a_verified_generation_model(settings, monkeypatch):
    local = settings.model_copy(update={"model_backend": "local"})
    monkeypatch.setattr(health, "model_check", unavailable)
    with TestClient(create_app(local)) as client:
        assert client.get("/ready").status_code == 503
    monkeypatch.setattr(health, "model_check", healthy)

    async def verified(_settings):
        return None

    monkeypatch.setattr(health, "verify_service", verified)
    with TestClient(create_app(local)) as client:
        assert client.get("/ready").status_code == 200


def test_invalid_cases_or_registry_fail_closed_without_leaking(settings, tmp_path):
    registry = tmp_path / "sources.yaml"
    registry.write_text("sources: invalid secret-config-value")
    (tmp_path / "broken.yaml").write_text("id: broken\nsecret: secret-case-value\n")
    broken = settings.model_copy(update={"source_registry_path": registry, "cases_path": tmp_path})
    with TestClient(create_app(broken)) as client:
        body = client.get("/api/status").json()
        assert body["registry"]["status"] == body["cases"]["status"] == "invalid"
        assert client.get("/ready").status_code == 503
        assert "broken.yaml" in body["cases"]["detail"]
        for path in ("/api/sources", "/api/cases"):
            response = client.get(path)
            assert response.status_code == 503
            assert "secret-config-value" not in response.text
            assert "secret-case-value" not in response.text


def test_source_catalogue_reports_casc_access_states(settings):
    with TestClient(create_app(settings)) as client:
        rows = client.get("/api/sources").json()["sources"]
    states = {row["source"]["id"]: row["access_state"] for row in rows}
    assert states["synthetic_fixtures"] == states["mrcpsych_casc"] == "in_use"
    assert states["nice"] == "awaiting_permission"
    assert states["bnf"] == "blocked"
