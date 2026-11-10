from psychiatry_api.cases import load_cases
from psychiatry_api.config import Settings
from psychiatry_api.evaluation.interpreter import evaluate, load_labels, score


def test_label_sets_name_real_cases_and_facts():
    cases = {case.id: {fact.id for fact in case.facts} for case in load_cases()}
    labels = load_labels()
    # Evaluation material is optional per station, but must name real cases.
    assert {label.case_id for label in labels} <= set(cases)
    assert {label.split for label in labels} == {"development", "test", "confirmation"}
    for label in labels:
        for item in label.items:
            assert set(item.expected) <= cases[label.case_id], item.utterance


def test_score_counts_spurious_selections_separately_from_misses():
    rows = [
        {"selected": ["a"], "expected": ["a"], "rapport": False, "expected_rapport": False},
        {"selected": ["a", "b"], "expected": ["a"], "rapport": True, "expected_rapport": False},
        {"selected": [], "expected": ["c"], "rapport": False, "expected_rapport": False},
    ]
    rows = [r | {"flags": [], "ms": 10} for r in rows]
    result = score(rows)
    assert result["exact_match"] == 1 / 3
    assert result["precision"] == 2 / 3 and result["recall"] == 2 / 3
    assert result["spurious_selections"] == 1 and result["items_with_spurious"] == 1
    assert result["rapport_accuracy"] == 2 / 3


async def test_keyword_backend_evaluates_without_a_model():
    report = await evaluate(Settings(_env_file=None), "fake", "test")
    assert report["interpreter"] == "keyword-v1"
    test_items = sum(len(s.items) for s in load_labels() if s.split == "test")
    assert set(report["by_split"]) == {"test"} and report["summary"]["items"] == test_items


def test_word_error_rate_parts():
    from psychiatry_api.evaluation.asr import content_words, edit_distance, normalise

    assert normalise("My favourite") == normalise("my favorite")
    assert normalise("My favourite", spelling=False) == ["my", "favourite"]
    assert normalise("Have you self-harmed? I’m asking.") == [
        "have",
        "you",
        "self",
        "harmed",
        "i'm",
        "asking",
    ]
    ref = normalise("Did you take the paracetamol last night")
    assert edit_distance(ref, normalise("Did you take paracetamol last night")) == 1
    assert edit_distance(ref, normalise("Did you take the paracetamol at night")) == 1
    assert edit_distance(ref, ref) == 0
    assert content_words(normalise("Did you take the paracetamol last night?")) == {
        "take",
        "paracetamol",
        "last",
        "night",
    }


def test_asr_summary_reports_corpus_wer_and_interpretation_effect():
    from psychiatry_api.evaluation.asr import summarise

    base = {"audio_ms": 2000, "asr_ms": 500, "content_words": 2}
    rows = [
        base
        | {
            "reference_words": 4,
            "errors": 0,
            "content_found": 2,
            "expected": ["a"],
            "selected_from_text": ["a"],
            "selected_from_speech": ["a"],
        },
        base
        | {
            "reference_words": 6,
            "errors": 3,
            "content_found": 1,
            "expected": ["b"],
            "selected_from_text": ["b"],
            "selected_from_speech": [],
        },
    ]
    result = summarise(rows)
    assert result["wer"] == 0.3 and result["exact_transcripts"] == 0.5
    assert result["content_word_recall"] == 0.75 and result["real_time_factor"] == 0.25
    assert result["typed_exact_match"] == 1.0 and result["speech_exact_match"] == 0.5
    assert result["speech_agrees_with_typed"] == 0.5


def test_confirmation_split_is_accepted_and_reported_separately():
    from psychiatry_api.evaluation.interpreter import SPLITS, LabelSet

    assert "confirmation" in SPLITS
    LabelSet.model_validate(
        {"case_id": "x", "case_version": "0.1.0", "split": "confirmation", "items": []}
    )
