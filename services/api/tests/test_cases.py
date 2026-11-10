import json

import pytest
from pydantic import ValidationError

from psychiatry_api.cases import CASES_PATH, Case, CaseSummary, load_case, load_cases
from psychiatry_api.sources import load_registry


@pytest.fixture
def raw_case() -> dict:
    return load_case(CASES_PATH / "elevated-mood-history.yaml").model_dump(mode="json")


def test_shipped_cases_load_and_target_a_permitted_blueprint(settings):
    cases = load_cases()
    assert cases
    registry = {
        source.id: source for source in load_registry(settings.source_registry_path).sources
    }
    for case in cases:
        source = registry[case.blueprint.source_id]
        assert any(item.version == case.blueprint.version for item in source.approved_items)
        assert case.authorship.clinically_validated is False


def test_summary_never_exposes_hidden_facts():
    case = load_case(CASES_PATH / "elevated-mood-history.yaml")
    summary = CaseSummary.of(case).model_dump_json()
    for fact in case.facts:
        assert fact.content not in summary


@pytest.mark.parametrize(
    ("path", "value", "message"),
    [
        (("timing", "reading_seconds"), 120, "Reading time"),
        (("timing", "interview_seconds"), 600, "seven minutes"),
        (("blueprint", "subdivision"), "formulation", "not a history subdivision"),
        (("blueprint", "version"), "February 2021", "pinned CASC blueprint"),
        (("authorship", "clinically_validated"), True, "clinically_validated"),
    ],
)
def test_blueprint_structure_is_enforced(raw_case, path, value, message):
    raw_case[path[0]][path[1]] = value
    with pytest.raises(ValidationError, match=message):
        Case.model_validate(raw_case)


def test_facts_need_question_labels_and_ids_must_be_unique(raw_case):
    gated = dict(raw_case["facts"][0], asked_about=[])
    with pytest.raises(ValidationError, match="asked_about"):
        Case.model_validate(raw_case | {"facts": [gated, *raw_case["facts"][1:]]})
    duplicate = dict(raw_case["facts"][1], id=raw_case["facts"][0]["id"])
    with pytest.raises(ValidationError, match="unique"):
        Case.model_validate(raw_case | {"facts": [raw_case["facts"][0], duplicate]})
    unkeyed = [dict(fact, key=False) for fact in raw_case["facts"]]
    with pytest.raises(ValidationError, match="key fact"):
        Case.model_validate(raw_case | {"facts": unkeyed})


def test_case_files_must_match_their_id_and_reject_duplicate_keys(tmp_path):
    source = (CASES_PATH / "elevated-mood-history.yaml").read_text()
    (tmp_path / "renamed.yaml").write_text(source)
    with pytest.raises(ValueError, match="named after its ID"):
        load_cases(tmp_path)
    (tmp_path / "renamed.yaml").unlink()
    (tmp_path / "elevated-mood-history.yaml").write_text(source + "\ntitle: Again\n")
    with pytest.raises(ValueError, match="Duplicate"):
        load_cases(tmp_path)


def test_cases_endpoint_lists_summaries_only(settings):
    from fastapi.testclient import TestClient

    from psychiatry_api.main import create_app

    response = TestClient(create_app(settings)).get("/api/cases")
    assert response.status_code == 200
    [summary] = [row for row in response.json() if row["id"] == "elevated-mood-history"]
    assert summary["reading_seconds"] == 90 and summary["clinically_validated"] is False
    assert "facts" not in summary and "three hours" not in response.text


def test_each_case_has_a_registered_character_and_installed_voice_unique_within_its_exam():
    """Within one running order (a mock exam of 16 stations) every character looks and
    sounds different; across running orders, characters and voices may be reused."""
    from psychiatry_api.catalogue import load as load_catalogue

    root = CASES_PATH.parents[1]
    avatars = {
        a["id"]: a
        for a in json.loads((root / "config/avatar-register.json").read_text())["avatars"]
    }
    voices = {
        v["name"] for v in json.loads((root / "config/tts-runtime.json").read_text())["voices"]
    }
    order_of = {
        s["existing_case"]: s["code"][0]
        for s in load_catalogue()["stations"]
        if s.get("existing_case")
    }
    by_order: dict[str, list] = {}
    for case in load_cases():
        persona = case.persona
        assert persona.avatar in avatars, case.id
        assert persona.voice.speaker in voices, case.id
        # The face, the voice and the hint agree on how the character presents.
        assert avatars[persona.avatar]["sex"] == persona.voice.sex, case.id
        assert persona.voice.speaker[1] == persona.voice.sex[0], case.id
        assert case.id in order_of, f"{case.id} is not in data/catalogue/stations.yaml"
        by_order.setdefault(order_of[case.id], []).append(case)
    for order, cases in by_order.items():
        faces = [c.persona.avatar for c in cases]
        speakers = [c.persona.voice.speaker for c in cases]
        assert len(faces) == len(set(faces)), f"running order {order} repeats a character"
        assert len(speakers) == len(set(speakers)), f"running order {order} repeats a voice"


@pytest.mark.parametrize(
    "filler",
    ["Mm.", "Hmmm.", "OK.", "Mm, right."],
)
def test_hesitations_are_short_fillers(raw_case, filler):
    raw_case["affect_stages"][0]["hesitations"] = [filler]
    assert Case.model_validate(raw_case).affect_stages[0].hesitations == (filler,)


@pytest.mark.parametrize(
    "filler",
    ["Three pints.", "", "...", "I took 40 tablets", "Well...", "I mean...", "Sorry...", "Daniel."],
)
def test_hesitations_cannot_carry_numbers_or_sentences(raw_case, filler):
    raw_case["affect_stages"][0]["hesitations"] = [filler]
    with pytest.raises(ValidationError):
        Case.model_validate(raw_case)
