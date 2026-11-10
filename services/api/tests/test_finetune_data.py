"""Data for the student interpreter: synthetic interviews must match their cases, follow
the runtime tone rules and stay clear of evaluation items; committed teacher labels may only
cover authored training lines (session transcripts stay local)."""

import difflib
import json

import yaml

from psychiatry_api.cases import load_cases
from psychiatry_api.config import ROOT
from psychiatry_api.finetune.build import TEACHER, authored, line_id
from psychiatry_api.finetune.format import Label, answer, parse, render
from psychiatry_api.roleplay.interpret import SPECIFIC_MIN_WORDS, challenging, quoted
from tests.test_training_data import TOO_CLOSE, evaluation_lines, norm

SYNTHETIC = ROOT / "data/finetune/synthetic"


def test_synthetic_interviews_match_cases_rules_and_stay_clear_of_evaluation():
    cases = {case.id: case for case in load_cases()}
    held = evaluation_lines()
    for path in sorted(SYNTHETIC.glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        case = cases[data["case_id"]]
        assert data["case_version"] == case.version, path.name
        facts = {fact.id for fact in case.facts}
        targets = [norm(line) for line in held.get(case.id, [])]
        seen = set()
        for interview in data["interviews"]:
            for turn in interview["turns"]:
                line, where = turn["doctor"], (path.name, interview["id"], turn["doctor"])
                assert norm(line) not in seen, f"duplicate line {where}"
                seen.add(norm(line))
                assert set(turn["topics"]) <= facts and len(turn["topics"]) <= 2, where
                assert turn["empathy"] in ("none", "brief", "specific"), where
                if turn["empathy"] == "none":
                    assert turn["empathy_words"] == "", where
                else:
                    assert quoted(turn["empathy_words"], line), where
                if turn["empathy"] == "specific":
                    assert len(turn["empathy_words"].split()) >= SPECIFIC_MIN_WORDS, where
                if turn["confrontational"]:
                    assert challenging(True, turn["confrontational_words"], line), where
                else:
                    assert turn["confrontational_words"] == "", where
                matcher = difflib.SequenceMatcher(None, b=norm(line))
                for target in targets:
                    matcher.set_seq1(target)
                    close = matcher.quick_ratio() >= TOO_CLOSE and matcher.ratio() >= TOO_CLOSE
                    assert not close, f"near-copy of an evaluation item: {where}"


def test_committed_teacher_labels_cover_only_authored_training_lines():
    if not TEACHER.exists():
        return
    known = {line_id(r["case_id"], r["utterance"]) for r in authored()}
    for row in map(json.loads, TEACHER.read_text().splitlines()):
        assert row["id"] in known, f"not an authored training line: {row['utterance']!r}"


def test_answers_round_trip_and_bad_answers_are_rejected():
    case = next(c for c in load_cases() if c.id == "alcohol-history")
    label = Label(frozenset({"quantity"}), "brief", "that sounds hard", False, "")
    assert parse(case, answer(case, label)) == label
    none = Label(frozenset(), "none", "", False, "")
    assert json.loads(answer(case, none))["t"] == ["none_of_these"]
    assert parse(case, answer(case, none)) == none
    for bad in (
        "not json",
        '{"t": ["no_such_topic"], "e": "none", "c": false}',
        '{"t": [], "e": "lots", "c": false}',
    ):
        assert parse(case, bad) is None
    prompt = render(case, "When did that start?", ("How much?", "A litre a day."))
    assert "Previous:" in prompt and prompt.endswith('Line: "When did that start?"')


STOCK_OPENINGS = (
    "thinking back to",
    "before we finish",
    "i'll pause there",
    "right just picking up",
    "could we go through",
    "i'd like to hear about",
)


def test_prompt_f_interviews_are_varied_and_cover_their_hard_cases():
    import collections

    for path in sorted(SYNTHETIC.glob("*.prompt-f.yaml")):
        data = yaml.safe_load(path.read_text())
        turns = [t for interview in data["interviews"] for t in interview["turns"]]
        openings = collections.Counter(" ".join(norm(t["doctor"]).split()[:3]) for t in turns)
        crowded = {o: n for o, n in openings.items() if n > 4}
        assert not crowded, f"{path.name}: openings used more than four times: {crowded}"
        for turn in turns:
            assert not norm(turn["doctor"]).startswith(STOCK_OPENINGS), (path.name, turn["doctor"])
        kinds = collections.Counter(t["kind"] for t in turns)
        assert kinds["near_miss"] >= 35 and kinds["confrontational"] >= 30, (path.name, kinds)
        assert kinds["reflection"] >= 25 and kinds["neighbour"] >= 20, (path.name, kinds)
        for turn in turns:
            if turn["kind"] == "near_miss":
                assert turn["topics"] == [], (path.name, turn["doctor"])
            if turn["kind"] == "confrontational":
                assert turn["confrontational"], (path.name, turn["doctor"])
            if turn["kind"] == "reflection":
                assert not turn["confrontational"], (path.name, turn["doctor"])


def test_tone_is_ruled_only_for_lines_the_runtime_rules_settle():
    from psychiatry_api.finetune.build import ruled

    assert ruled("How much do you drink on a typical day?")
    assert ruled("Sorry, and when did that start?")
    assert not ruled("That sounds hard. How are you sleeping?")  # empathy needs a model
    assert not ruled("Why didn't you tell anyone?")  # can be confrontational
    assert not ruled("You knew this was coming, didn't you?")
    assert not ruled("I wondered how your sleep has been")


def test_boundary_pairs_rank_by_similarity_with_a_bonus_for_confusions():
    from collections import Counter

    from psychiatry_api.cases import CASES_PATH, load_case
    from psychiatry_api.finetune.pairs import PER_STATION, choose

    case = load_case(CASES_PATH / "alcohol-history.yaml")
    ids = sorted(f.id for f in case.facts)
    pairs = [(a, b) for i, a in enumerate(ids) for b in ids[i + 1 :]]
    similar = {(case.id, *p): n / 100 for n, p in enumerate(pairs)}  # the last most similar
    # One confusion nudges a pair up; a pair confused repeatedly is always kept.
    confused = Counter({(case.id, *pairs[-2]): 1, (case.id, *pairs[0]): 2})
    picked = [tuple(p["facts"]) for p in choose(case, similar, confused)]
    assert picked[:PER_STATION] == [pairs[-2], pairs[-1], pairs[-3], pairs[-4]]
    assert picked[PER_STATION:] == [pairs[0]]
