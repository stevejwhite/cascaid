from psychiatry_api.cases import load_cases
from psychiatry_api.evaluation.baseline import NullInterpreter, full_case_sheet
from psychiatry_api.evaluation.leaks import flags, stems
from psychiatry_api.roleplay.disclosure import DisclosureState, Interpretation


def case(case_id):
    return next(c for c in load_cases() if c.id == case_id)


def test_full_case_sheet_holds_every_fact_with_its_rule():
    station = case("overdose-risk-assessment")
    sheet = full_case_sheet(station)
    for fact in station.facts:
        assert fact.content in sheet
    assert "[ONLY AFTER EMPATHY] My mum and my younger brother" in sheet


async def test_null_interpreter_unlocks_nothing():
    result = await NullInterpreter().interpret(case("alcohol-history"), DisclosureState(), [], "Hi")
    assert result == (Interpretation(), [], [])


def test_leak_screen_needs_distinctive_content_not_common_words():
    station = case("elevated-mood-history")
    allowed = {"new-business", "past-low-period"}
    assert flags(station, allowed, "Any past problems?", "I don't think about that, really.") == []
    leaked = flags(
        station, allowed, "Tell me more", "I sleep about three hours a night these days."
    )
    assert leaked == ["sleep-reduced"]
    assert "#3" in stems("three hours") and "think" not in stems("I think so")
