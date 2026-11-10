from fastapi.testclient import TestClient

from psychiatry_api import catalogue
from psychiatry_api.cases import BLUEPRINT_VERSION
from psychiatry_api.main import create_app


def test_matrix_uses_pinned_catalogue_and_only_public_station_fields(settings):
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/blueprint")
        assert response.status_code == 200
        body = response.json()
        cases = {case["id"]: case for case in client.get("/api/cases").json()}
    assert body["version"] == BLUEPRINT_VERSION
    assert body["stations_per_running_order"] == {"history": 5, "examination": 5, "management": 6}
    assert len(body["subdivisions"]) == 17
    assert len(body["stations"]) == 64
    rows = {row["code"]: row for row in body["stations"]}
    assert rows["A09"]["case_id"] == "alcohol-history"
    assert rows["A09"]["session"] == "afternoon"
    assert rows["B08"]["case_id"] is None
    assert rows["D16"]["case_id"] is None
    assert "Physical examination" in rows["B08"]["unavailable_reason"]
    assert rows["C08"]["case_id"] is None
    for row in rows.values():
        assert set(row) == {
            "code",
            "running_order",
            "session",
            "skill",
            "subdivision",
            "specialty",
            "title",
            "case_id",
            "unavailable_reason",
            "clinically_validated",
        }
        if row["case_id"]:
            case = cases[row["case_id"]]
            assert row["title"] == case["title"]
            assert row["specialty"] == case["specialty"]
            assert row["unavailable_reason"] is None


def test_missing_case_files_are_not_selectable(settings, tmp_path):
    empty = settings.model_copy(update={"cases_path": tmp_path})
    with TestClient(create_app(empty)) as client:
        response = client.get("/api/blueprint")
    assert response.status_code == 200
    assert all(row["case_id"] is None for row in response.json()["stations"])
    assert all(row["unavailable_reason"] for row in response.json()["stations"])


def test_invalid_blueprint_is_an_error_without_exposing_author_data(settings, monkeypatch):
    data = catalogue.load()
    data["blueprint"]["version"] = "private-author-value"
    monkeypatch.setattr(catalogue, "load", lambda: data)
    with TestClient(create_app(settings)) as client:
        response = client.get("/api/blueprint")
    assert response.status_code == 503
    assert "private-author-value" not in response.text


def test_mismatched_case_mapping_fails_closed(settings, monkeypatch):
    data = catalogue.load()
    data["stations"][0]["existing_case"] = "alcohol-history"
    monkeypatch.setattr(catalogue, "load", lambda: data)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/blueprint").status_code == 503
