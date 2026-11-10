"""The station catalogue must follow the pinned CASC blueprint: the shape of every running
order, the minimum frequency of every subdivision, and the range of clinical scenarios."""

from collections import Counter

from psychiatry_api.cases import BLUEPRINT_SOURCE_ID, SUBDIVISIONS, load_cases
from psychiatry_api.catalogue import DOC, load, render, running_orders

CATALOGUE = load()
BLUEPRINT = CATALOGUE["blueprint"]
STATIONS = CATALOGUE["stations"]
ORDERS = running_orders(CATALOGUE)


def patient_age(station: dict) -> str:
    if station["meets"]["role"] == "patient":
        return station["meets"]["age_band"]
    return station["patient_age_band"]


def test_station_codes_and_blueprint_slots_are_valid():
    codes = [s["code"] for s in STATIONS]
    assert len(codes) == len(set(codes))
    assert BLUEPRINT["source_id"] == BLUEPRINT_SOURCE_ID
    specialties = set(BLUEPRINT["minimum_specialty"])
    for s in STATIONS:
        assert s["subdivision"] in SUBDIVISIONS[s["skill"]], s["code"]
        assert s["specialty"] in specialties, s["code"]
        assert s["communication"] in BLUEPRINT["communication_emphasis"], s["code"]
        assert s["condition"] in CATALOGUE["coverage"]["condition_groups"], s["code"]
        assert s["setting"] in CATALOGUE["coverage"]["settings"], s["code"]
        assert s["meets"]["role"] in CATALOGUE["coverage"]["roles"], s["code"]
        assert s["meets"]["age_band"] in CATALOGUE["coverage"]["age_bands"], s["code"]
        assert patient_age(s) in CATALOGUE["coverage"]["age_bands"], s["code"]
        for field in ("scenario", "task", "covers"):
            assert s[field], (s["code"], field)


def test_every_running_order_has_the_exam_shape():
    for code, order in ORDERS.items():
        assert Counter(s["skill"] for s in order) == BLUEPRINT["stations_per_running_order"], code
        for session, spec in BLUEPRINT["sessions"].items():
            in_session = [s for s in order if s["session"] == session]
            assert Counter(s["skill"] for s in in_session) == spec["stations"], (code, session)


def test_every_running_order_meets_the_specialty_and_communication_minimums():
    for code, order in ORDERS.items():
        specialties = Counter(s["specialty"] for s in order)
        for specialty, minimum in BLUEPRINT["minimum_specialty"].items():
            assert specialties[specialty] >= minimum, (code, specialty)
        emphases = {s["communication"] for s in order}
        assert emphases >= set(BLUEPRINT["communication_emphasis"]), code


def test_every_running_order_includes_each_required_group():
    for code, order in ORDERS.items():
        present = {s["subdivision"] for s in order}
        for group in BLUEPRINT["at_least_one_of"]:
            assert present & set(group), (code, group)


def test_subdivisions_meet_their_minimum_share_of_running_orders():
    for subdivision, minimum in BLUEPRINT["minimum_percentage"].items():
        present = sum(any(s["subdivision"] == subdivision for s in o) for o in ORDERS.values())
        assert 100 * present / len(ORDERS) >= minimum, (subdivision, present)
    # Every subdivision in the blueprint has a minimum.
    every = set().union(*SUBDIVISIONS.values())
    assert set(BLUEPRINT["minimum_percentage"]) == every


def test_the_set_covers_the_syllabus_range_of_clinical_scenarios():
    coverage = CATALOGUE["coverage"]
    assert {s["condition"] for s in STATIONS} == set(coverage["condition_groups"])
    assert {s["setting"] for s in STATIONS} == set(coverage["settings"])
    assert {s["meets"]["role"] for s in STATIONS} == set(coverage["roles"])
    # Patients of every age: the person met, or the patient they speak for.
    assert {patient_age(s) for s in STATIONS} == set(coverage["age_bands"])


def test_existing_cases_match_their_catalogue_slots():
    cases = {c.id: c for c in load_cases()}
    reading = {name: spec["reading_seconds"] for name, spec in BLUEPRINT["sessions"].items()}
    mapped = [s for s in STATIONS if s.get("existing_case")]
    assert {s["existing_case"] for s in mapped} == set(cases)
    for s in mapped:
        case = cases[s["existing_case"]]
        assert case.blueprint.skill == s["skill"], s["code"]
        assert case.blueprint.subdivision == s["subdivision"], s["code"]
        assert case.blueprint.specialty == s["specialty"], s["code"]
        assert case.timing.reading_seconds == reading[s["session"]], s["code"]
        assert s["communication"] in case.blueprint.communication_focus, s["code"]


def test_the_catalogue_document_is_up_to_date():
    assert DOC.read_text() == render(CATALOGUE), "Run npm run catalogue:doc"
