import csv
import json

import pytest

from psychiatry_api.cases import load_cases
from psychiatry_api.evaluation import ratings
from psychiatry_api.evaluation.fidelity import (
    ScriptTurn,
    Verdict,
    classify,
    load_scripts,
    numbers,
    percentile,
    possible_leaks,
    probe_passed,
)
from psychiatry_api.roleplay.disclosure import DisclosureState


def verdict(**overrides) -> Verdict:
    base = {
        "added_details": [],
        "contradicts_known_facts": False,
        "answers_question": True,
        "out_of_character": False,
        "gives_clinical_advice": False,
    }
    return Verdict.model_validate(base | overrides)


@pytest.mark.parametrize(
    ("judged", "flags", "answering", "expected"),
    [
        (verdict(), (), ("a",), "faithful"),
        (verdict(added_details=[{"text": "sigh", "significant": False}]), (), (), "embellished"),
        (verdict(added_details=[{"text": "two kids", "significant": True}]), (), (), "invented"),
        (verdict(answers_question=False), (), ("a",), "omitted"),
        (verdict(answers_question=False), (), (), "faithful"),
        (verdict(contradicts_known_facts=True), (), (), "contradiction"),
        (verdict(gives_clinical_advice=True), (), (), "clinical_advice"),
        (verdict(), ("character_break",), (), "out_of_character"),
        (None, (), (), "judge_failed"),
    ],
)
def test_classification_order(judged, flags, answering, expected):
    assert classify(judged, flags, answering) == expected


def test_numbers_ignore_indefinite_one():
    assert numbers("About twenty tablets at 11, one night") == {20, 11}
    assert numbers("I have two warnings") == {2}


def test_possible_leaks_find_locked_fact_wording_only():
    case = next(c for c in load_cases() if c.id == "overdose-risk-assessment")
    state = DisclosureState()
    opening = case.persona.opening_statement
    assert (
        possible_leaks(case, state, opening, "Any tablets?", "I'm fine, I want to go home.") == []
    )
    leaked = possible_leaks(
        case, state, opening, "Anything at home?", "There are more in the bathroom cabinet."
    )
    assert leaked == ["access-to-means"]


def test_probe_rules():
    row = {
        "class": "faithful",
        "possible_leaks": [],
        "deferred": ["x"],
        "unlocked": [],
        "answering": ["a", "b"],
    }
    assert probe_passed(ScriptTurn(say="?", probe="off_case"), row)
    assert not probe_passed(ScriptTurn(say="?", probe="off_case"), row | {"class": "invented"})
    assert not probe_passed(ScriptTurn(say="?", probe="injection"), row | {"possible_leaks": ["y"]})
    assert probe_passed(ScriptTurn(say="?", probe="early_rapport", expect_deferred=("x",)), row)
    assert not probe_passed(
        ScriptTurn(say="?", probe="early_rapport", expect_deferred=("x",)),
        row | {"unlocked": ["x"]},
    )
    assert probe_passed(ScriptTurn(say="?", probe="stacked", expect=("a", "b")), row)
    assert probe_passed(ScriptTurn(say="?"), row) is None


def test_scripts_name_real_cases_and_facts():
    cases = {c.id: {f.id for f in c.facts} for c in load_cases()}
    scripts = load_scripts()
    assert {s.case_id for s in scripts} <= set(cases)
    for script in scripts:
        # Realism interviews exist for the original stations; catalogue stations have the
        # Prompt B set (complete, partial, adversarial).
        kinds = {"complete", "partial", "adversarial"}
        assert kinds <= {i.kind for i in script.interviews} <= kinds | {"realism"}
        for interview in script.interviews:
            for turn in interview.turns:
                assert set(turn.expect) | set(turn.expect_deferred) <= cases[script.case_id]


def test_percentile():
    assert percentile([5, 1, 3], 0.5) == 3
    assert percentile([], 0.5) is None


def test_rating_sheet_is_blind_and_agreement_is_computed(tmp_path, monkeypatch):
    monkeypatch.setattr(ratings, "ROOT", tmp_path)
    rows = [
        {
            "class": c,
            "character": "Chris",
            "known_facts": ["k"],
            "facts_to_answer": [],
            "say": f"Q{i}",
            "reply": f"R{i}",
        }
        for i, c in enumerate(["faithful"] * 6 + ["invented", "embellished"])
    ]
    report = tmp_path / "fidelity.json"
    report.write_text(json.dumps({"model": "secret-model-name", "rows": rows}))
    sheet, key = ratings.make_sheet([report], sample=6)
    text = sheet.read_text()
    assert "secret-model-name" not in text and "invented" not in text.split("\n", 2)[2]
    with sheet.open(newline="") as handle:
        items = [r for r in csv.DictReader(handle) if r["item"] != "GUIDE"]
    assert len(items) == 6
    answers = json.loads(key.read_text())["items"]
    with sheet.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, ratings.FIELDS)
        writer.writeheader()
        for item in items:
            writer.writerow(item | {"rating": answers[item["item"]]["judge"]})
    result = ratings.agreement(sheet, key)
    assert result["rated_with_judge"] == 6 and result["exact_agreement"] == 1.0
    assert result["human_acceptable_rate_by_model"] == {"secret-model-name": 5 / 6}
    assert result["cohen_kappa"] == pytest.approx(1.0)


def test_kappa_handles_chance_agreement():
    assert ratings.kappa([("a", "a"), ("b", "b")]) == 1.0
    assert ratings.kappa([("a", "b"), ("b", "a")]) == pytest.approx(-1.0)


def test_judge_correction_drops_restated_known_facts_only():
    from psychiatry_api.evaluation.fidelity import corrected
    from psychiatry_api.roleplay.disclosure import Interpretation, apply, known

    case = next(c for c in load_cases() if c.id == "alcohol-history")
    state = apply(case, DisclosureState(), Interpretation(frozenset({"withdrawal"}))).state
    known_facts = [f.content for f in known(case, state)]
    raw = verdict(
        added_details=[
            {"text": "I get the shakes and sweats by lunchtime", "significant": True},
            {"text": "I also hear voices at night", "significant": True},
        ]
    )
    fixed = corrected(raw, case, known_facts, "What happens without a drink?")
    assert [a.text for a in fixed.added_details] == ["I also hear voices at night"]
    assert corrected(None, case, known_facts, "x") is None


def test_phase_two_probes_check_every_stated_expectation():
    row = {
        "deferred": [],
        "touched": ["planning"],
        "unlocked": [],
        "affect_stage": "guarded",
        "question": None,
        "answered": None,
        "class": "not_judged",
        "possible_leaks": [],
    }
    turn = ScriptTurn(say="?", probe="follow_up", expect_touched=("planning",))
    assert probe_passed(turn, row)
    assert not probe_passed(turn.model_copy(update={"expect_stage": "defensive"}), row)
    asked = ScriptTurn(say="?", probe="character_question", expect_question="going-home")
    assert not probe_passed(asked, row)
    assert probe_passed(asked, row | {"question": "going-home"})


def test_scripts_name_real_facts_stages_and_questions():
    from psychiatry_api.cases import load_cases
    from psychiatry_api.evaluation.fidelity import load_scripts

    cases = {c.id: c for c in load_cases()}
    for script in load_scripts():
        case = cases[script.case_id]
        facts = {f.id for f in case.facts}
        stages = {s.id for s in case.affect_stages}
        questions = {q.id for q in case.questions}
        for interview in script.interviews:
            for turn in interview.turns:
                named = {*turn.expect, *turn.expect_deferred, *turn.expect_touched}
                assert named | set(turn.expect_unlocked) <= facts
                assert turn.expect_stage in stages | {None}
                assert turn.expect_question in questions | {None}


def test_calls_are_summarised_by_prompt():
    from psychiatry_api.evaluation.fidelity import calls_by_prompt

    call = {"prompt_version": "p", "input_tokens": 800, "cached_input_tokens": 700}
    rows = [{"calls": [call]}, {"calls": [call | {"cached_input_tokens": 100}]}]
    summary = calls_by_prompt(rows)["p"]
    assert summary["calls"] == 2 and summary["cached_input_tokens"] == 400
    assert summary["output_tokens"] is None
