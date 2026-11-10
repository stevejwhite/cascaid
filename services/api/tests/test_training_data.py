"""Training data for the topic classifier must match its cases and stay clear of every
evaluation item; training on near-copies of held-out questions would inflate results."""

import difflib
import re
from pathlib import Path

import yaml

from psychiatry_api.cases import load_cases
from psychiatry_api.config import ROOT

TRAINING = ROOT / "data/training/topics"
TONE = ROOT / "data/training/tone"
EVALUATION = ROOT / "data/evaluation"
# Lines at least this similar (difflib ratio on normalised words) count as near-copies.
TOO_CLOSE = 0.75


def norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z']+", text.lower()))


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def evaluation_lines() -> dict[str, list[str]]:
    lines: dict[str, list[str]] = {}
    for path in (EVALUATION / "interpreter").glob("*.yaml"):
        data = load(path)
        lines.setdefault(data["case_id"], []).extend(i["utterance"] for i in data["items"])
    for path in (EVALUATION / "scripts").glob("*.yaml"):
        data = load(path)
        said = [t["say"] for interview in data["interviews"] for t in interview["turns"]]
        lines.setdefault(data["case_id"], []).extend(said)
    for path in (EVALUATION / "rapport").glob("*.yaml"):
        for item in load(path)["items"]:
            lines.setdefault(item["case_id"], []).append(item["utterance"])
    return lines


def test_training_files_match_their_cases():
    cases = {case.id: case for case in load_cases()}
    by_case: dict[str, list[str]] = {}
    for path in sorted(TRAINING.glob("*.yaml")):
        data = load(path)
        case = cases[data["case_id"]]
        assert data["case_version"] == case.version, path.name
        assert data["status"] in ("reviewed", "draft"), path.name
        facts = {fact.id for fact in case.facts}
        texts = [norm(item["utterance"]) for item in data["items"]]
        by_case.setdefault(case.id, []).extend(texts)
        for item in data["items"]:
            assert set(item["topics"]) <= facts, (path.name, item["utterance"])
            assert len(item["topics"]) <= 2, (path.name, item["utterance"])
    # A case's lines may be spread over several files; none may repeat across them.
    for case_id, texts in by_case.items():
        repeated = {t for t in texts if texts.count(t) > 1}
        assert not repeated, f"{case_id}: duplicate lines {sorted(repeated)[:3]}"


def test_no_training_line_is_a_near_copy_of_an_evaluation_item():
    held = evaluation_lines()
    close = []
    for path in sorted([*TRAINING.glob("*.yaml"), *TONE.glob("*.yaml")]):
        data = load(path)
        targets = [norm(line) for line in held.get(data["case_id"], [])]
        for item in data["items"]:
            line = norm(item["utterance"])
            matcher = difflib.SequenceMatcher(None, b=line)
            for target in targets:
                matcher.set_seq1(target)
                if matcher.quick_ratio() >= TOO_CLOSE and matcher.ratio() >= TOO_CLOSE:
                    close.append((path.name, item["utterance"]))
                    break
    assert not close, f"{len(close)} near-copies of evaluation items: {close[:5]}"


def test_tone_labels_agree_with_the_runtime_rules():
    from psychiatry_api.roleplay.interpret import SPECIFIC_MIN_WORDS, challenging, quoted

    cases = {case.id: case for case in load_cases()}
    for path in sorted(TONE.glob("*.yaml")):
        data = load(path)
        assert data["case_version"] == cases[data["case_id"]].version, path.name
        texts = [norm(item["utterance"]) for item in data["items"]]
        assert len(texts) == len(set(texts)), f"{path.name}: duplicate lines"
        for item in data["items"]:
            line, empathy = item["utterance"], item["empathy"]
            where = (path.name, line)
            assert empathy in (0, 1, 2) and isinstance(item["confrontational"], bool), where
            assert not (empathy and item["confrontational"]), where
            if empathy:
                assert quoted(item["empathy_words"], line), where
            else:
                assert item["empathy_words"] == "", where
            if empathy == 2:
                assert len(item["empathy_words"].split()) >= SPECIFIC_MIN_WORDS, where
            if item["confrontational"]:
                assert challenging(True, item["challenge_words"], line), where
            else:
                assert item["challenge_words"] == "", where
