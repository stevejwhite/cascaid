"""Score the deterministic communication indicators against author labels.

Usage: npm run eval:indicators -- [--out artifacts/eval/indicators.json]

The test split was committed before the rules were written, but the same author wrote
both, so it is not blind: report it as a consistency check, not independent validation.
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml

from psychiatry_api.config import ROOT
from psychiatry_api.domain import Contract
from psychiatry_api.feedback.indicators import INDICATORS_VERSION, tag
from psychiatry_api.sources import UniqueKeyLoader

LABELS = ROOT / "data/evaluation/indicators"


class Item(Contract):
    text: str
    question: Literal["open", "closed", "none"]
    summary: bool
    check_understanding: bool


class LabelSet(Contract):
    split: Literal["development", "test"]
    items: tuple[Item, ...]


def load_labels(root: Path = LABELS) -> tuple[LabelSet, ...]:
    return tuple(
        LabelSet.model_validate(yaml.load(path.read_text(), Loader=UniqueKeyLoader))
        for path in sorted(root.glob("*.yaml"))
    )


def binary(rows: list[dict], field: str) -> dict:
    tp = sum(r[field] and r[f"expected_{field}"] for r in rows)
    fp = sum(r[field] and not r[f"expected_{field}"] for r in rows)
    fn = sum(not r[field] and r[f"expected_{field}"] for r in rows)
    return {
        "positives": tp + fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
        "false_positives": fp,
        "false_negatives": fn,
    }


def score(rows: list[dict]) -> dict:
    kinds = ("open", "closed", "none")
    return {
        "items": len(rows),
        "question_type_accuracy": sum(r["question"] == r["expected_question"] for r in rows)
        / len(rows),
        "question_type_confusion": {
            expected: {
                got: sum(r["expected_question"] == expected and r["question"] == got for r in rows)
                for got in kinds
            }
            for expected in kinds
        },
        "summary": binary(rows, "summary"),
        "check_understanding": binary(rows, "check_understanding"),
        "all_correct": sum(
            r["question"] == r["expected_question"]
            and r["summary"] == r["expected_summary"]
            and r["check_understanding"] == r["expected_check_understanding"]
            for r in rows
        )
        / len(rows),
    }


def evaluate() -> dict:
    rows = []
    for label_set in load_labels():
        for item in label_set.items:
            tags = tag(item.text)
            rows.append(
                {
                    "split": label_set.split,
                    "text": item.text,
                    "question": tags.question,
                    "expected_question": item.question,
                    "summary": tags.summary,
                    "expected_summary": item.summary,
                    "check_understanding": tags.check_understanding,
                    "expected_check_understanding": item.check_understanding,
                }
            )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "rules_version": INDICATORS_VERSION,
        "by_split": {
            split: score([r for r in rows if r["split"] == split])
            for split in ("development", "test")
            if any(r["split"] == split for r in rows)
        },
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = evaluate()
    for row in report["rows"]:
        if (row["question"], row["summary"], row["check_understanding"]) != (
            row["expected_question"],
            row["expected_summary"],
            row["expected_check_understanding"],
        ):
            print(
                f"MISS [{row['split']}] {row['text']!r}: {row['question']}, summary="
                f"{row['summary']}, check={row['check_understanding']} (expected "
                f"{row['expected_question']}, {row['expected_summary']}, "
                f"{row['expected_check_understanding']})"
            )
    print(json.dumps(report["by_split"], indent=2))
    if args.out:
        out = args.out if args.out.is_absolute() else ROOT / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
