from psychiatry_api.evaluation.classifier import pick_threshold, topic_outcomes
from psychiatry_api.roleplay.classify import NO_TOPIC as NONE
from psychiatry_api.roleplay.classify import (
    TopicItem,
    challenge_text,
    decide,
    stacked,
    statements,
)


def test_a_confident_answer_is_kept_and_anything_else_defers():
    assert decide("Did you leave a note?", "note", 0.95, 0.9) == frozenset({"note"})
    assert decide("Hello there.", NONE, 0.97, 0.9) == frozenset()
    assert decide("Did you leave a note?", "note", 0.6, 0.9) is None
    # Two questions in one line always go to the model interpreter.
    assert stacked("Do you drink? Do you smoke?")
    assert decide("Do you drink? Do you smoke?", "alcohol", 0.99, 0.9) is None


def test_threshold_keeps_accepted_accuracy_at_the_qwen_level():
    note = TopicItem("c", "Did you leave a note?", frozenset({"note"}))
    rows = [(note, "note", 0.95)] * 97 + [(note, "trigger", 0.7)] * 3
    # 97% exact at 0.6 is below the 98.5% bar; above 0.7 the wrong answers are deferred.
    assert topic_outcomes(rows, 0.6) == (100, 97, 3)
    assert pick_threshold(rows) == 0.75


def test_tone_text_follows_the_runtime_rules():
    line = "That sounds hard. How have you been sleeping?"
    assert statements(line) == "That sounds hard."
    assert challenge_text("How much do you drink?") == ""
    assert challenge_text("Surely you knew?") == "Surely you knew?"
