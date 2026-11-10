from psychiatry_api.evaluation.rapport import load_labels, score


def test_label_sets_load_and_cover_every_level():
    for split in ("development", "test"):
        items = load_labels(split).items
        assert {i.empathy for i in items} == {0, 1, 2}
        assert any(i.confrontational for i in items)


def test_score_compares_a_v1_flag_as_any_empathy():
    rows = [
        {
            "empathy": 0,
            "confrontational": True,
            "rated": 1,
            "rated_empathy": None,
            "rated_confrontational": None,
        },
        {
            "empathy": 2,
            "confrontational": False,
            "rated": 1,
            "rated_empathy": None,
            "rated_confrontational": None,
        },
    ]
    result = score(rows)
    assert result["rapport_accuracy"] == 0.5 and result["rapport_false_positives"] == 1
    assert result["level_accuracy"] is None and result["confrontational_recall"] is None
