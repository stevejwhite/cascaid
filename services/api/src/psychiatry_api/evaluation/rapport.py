"""Score an interpreter's empathy and confrontation ratings against author labels.

Usage: npm run eval:rapport -- [--split test|development] [--model registered|<id>] [--out PATH]

Labels: data/evaluation/rapport (test is held out). An interpreter without graded empathy
(casc-interpret-v1) is scored on its rapport flag only, as empathy 1 when set.
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml

from psychiatry_api.cases import load_cases
from psychiatry_api.config import ROOT, Settings
from psychiatry_api.domain import Contract
from psychiatry_api.evaluation.interpreter import Previous
from psychiatry_api.evaluation.models import REGISTERED, resolve
from psychiatry_api.roleplay.classify import build_cascade
from psychiatry_api.roleplay.disclosure import DisclosureState
from psychiatry_api.roleplay.interpret import ModelInterpreter
from psychiatry_api.sources import UniqueKeyLoader

LABELS = ROOT / "data/evaluation/rapport"


class Item(Contract):
    case_id: str
    utterance: str
    empathy: Literal[0, 1, 2]
    confrontational: bool
    previous: Previous | None = None


class LabelSet(Contract):
    split: Literal["development", "test"]
    items: tuple[Item, ...]


def load_labels(split: str) -> LabelSet:
    path = LABELS / f"{split}.yaml"
    return LabelSet.model_validate(yaml.load(path.read_text(), Loader=UniqueKeyLoader))


def score(rows: list[dict]) -> dict:
    def rate(hits: int, total: int) -> float | None:
        return hits / total if total else None

    shown = [r for r in rows if r["empathy"] > 0]
    none = [r for r in rows if r["empathy"] == 0]
    graded = [r for r in rows if r["rated_empathy"] is not None]
    confront = [r for r in rows if r["rated_confrontational"] is not None]
    return {
        "items": len(rows),
        # Any empathy (level 1 or 2), comparable with the v1 rapport flag.
        "rapport_accuracy": rate(
            sum((r["rated"] > 0) == (r["empathy"] > 0) for r in rows), len(rows)
        ),
        "rapport_false_positives": sum(r["rated"] > 0 for r in none),
        "rapport_false_negatives": sum(r["rated"] == 0 for r in shown),
        "level_accuracy": rate(sum(r["rated"] == r["empathy"] for r in graded), len(graded))
        if graded
        else None,
        "confusion": {
            f"{e}->{g}": sum(r["empathy"] == e and r["rated"] == g for r in graded)
            for e in (0, 1, 2)
            for g in (0, 1, 2)
        }
        if graded
        else None,
        "confrontational_precision": rate(
            sum(r["confrontational"] and r["rated_confrontational"] for r in confront),
            sum(bool(r["rated_confrontational"]) for r in confront),
        )
        if confront
        else None,
        "confrontational_recall": rate(
            sum(r["confrontational"] and r["rated_confrontational"] for r in confront),
            sum(r["confrontational"] for r in confront),
        )
        if confront
        else None,
    }


async def evaluate(
    settings: Settings, split: str, model_name: str, interpreter_kind: str = "model"
) -> dict:
    model, model_label = await resolve(settings, model_name)
    interpreter = ModelInterpreter(model, int(settings.model_timeout_seconds * 1000))
    cases = {case.id: case for case in load_cases(settings.cases_path)}
    if interpreter_kind == "cascade":
        interpreter = build_cascade(settings, interpreter, cases)
    rows = []
    for item in load_labels(split).items:
        history = [(item.previous.interviewer, item.previous.character)] if item.previous else []
        interpretation, _, flags = await interpreter.interpret(
            cases[item.case_id], DisclosureState(), history, item.utterance
        )
        graded = getattr(interpretation, "empathy", None)
        rows.append(
            {
                "case_id": item.case_id,
                "utterance": item.utterance,
                "empathy": item.empathy,
                "confrontational": item.confrontational,
                "rated": graded if graded is not None else int(interpretation.rapport),
                "rated_empathy": graded,
                "rated_confrontational": getattr(interpretation, "confrontational", None),
                "flags": flags,
                "tone_route": interpretation.tone_route,
            }
        )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "split": split,
        "model": model_label,
        "interpreter_prompt": interpreter.prompt_version,
        "summary": score(rows),
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--split", choices=("development", "test"), default="test")
    parser.add_argument("--model", default=REGISTERED)
    parser.add_argument("--interpreter", choices=("model", "cascade"), default="cascade")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = asyncio.run(evaluate(Settings(), args.split, args.model, args.interpreter))
    for row in result["rows"]:
        wrong = row["rated"] != row["empathy"] or (
            row["rated_confrontational"] is not None
            and row["rated_confrontational"] != row["confrontational"]
        )
        if wrong:
            print(
                f"MISS {row['case_id']}: {row['utterance']!r}\n"
                f"     expected empathy={row['empathy']} confrontational={row['confrontational']} "
                f"rated={row['rated']} confrontational={row['rated_confrontational']}"
            )
    print(json.dumps(result["summary"], indent=2))
    if args.out:
        out = args.out if args.out.is_absolute() else ROOT / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
