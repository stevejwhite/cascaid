"""Score an interpreter against author-labelled utterances.

Usage: npm run eval:interpreter -- [--backend fake|local] [--out artifacts/eval/interpreter.json]

Metrics need no clinical judgement: they compare selected fact IDs with the labels.
Spurious selections matter most, because each one can unlock a hidden fact early.
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Literal

import yaml

from psychiatry_api.cases import load_cases
from psychiatry_api.config import ROOT, Settings
from psychiatry_api.domain import Contract
from psychiatry_api.evaluation.models import REGISTERED, resolve
from psychiatry_api.roleplay.classify import build_cascade
from psychiatry_api.roleplay.disclosure import DisclosureState
from psychiatry_api.roleplay.interpret import KeywordInterpreter, ModelInterpreter
from psychiatry_api.sources import UniqueKeyLoader

LABELS = ROOT / "data/evaluation/interpreter"


class Previous(Contract):
    interviewer: str
    character: str


class Item(Contract):
    utterance: str
    expected: tuple[str, ...]
    rapport: bool
    previous: Previous | None = None


class LabelSet(Contract):
    case_id: str
    # The case version the items were written for; tests require it to match the case.
    case_version: str
    # development sets may be used for tuning; report test sets as held-out results.
    # confirmation: a held-out set used once per candidate, at the end
    # (docs/STUDENT-CROSS-CHECK-PLAN.md).
    split: Literal["development", "test", "confirmation"]
    items: tuple[Item, ...]


SPLITS = ("development", "test", "confirmation")

# The original stations' label sets. Speech recordings and word error rate are measured on
# these only, so recording item numbers and results stay comparable as stations are added.
SPEECH_CASES = frozenset(
    {
        "alcohol-history",
        "clozapine-explanation-relative",
        "elevated-mood-history",
        "memory-collateral-history",
        "overdose-risk-assessment",
    }
)


def speech_labels() -> tuple[LabelSet, ...]:
    return tuple(label for label in load_labels() if label.case_id in SPEECH_CASES)


def load_labels(root: Path = LABELS) -> tuple[LabelSet, ...]:
    return tuple(
        LabelSet.model_validate(yaml.load(path.read_text(), Loader=UniqueKeyLoader))
        for path in sorted(root.glob("*.yaml"))
    )


def score(rows: list[dict]) -> dict:
    selected = sum(len(r["selected"]) for r in rows)
    expected = sum(len(r["expected"]) for r in rows)
    correct = sum(len(set(r["selected"]) & set(r["expected"])) for r in rows)
    return {
        "items": len(rows),
        "exact_match": sum(set(r["selected"]) == set(r["expected"]) for r in rows) / len(rows),
        "precision": correct / selected if selected else 1.0,
        "recall": correct / expected if expected else 1.0,
        "spurious_selections": selected - correct,
        "items_with_spurious": sum(bool(set(r["selected"]) - set(r["expected"])) for r in rows),
        "rapport_accuracy": sum(r["rapport"] == r["expected_rapport"] for r in rows) / len(rows),
        "failures": sum("interpretation_failed" in r["flags"] for r in rows),
        "mean_ms": round(sum(r["ms"] for r in rows) / len(rows)),
    }


async def evaluate(
    settings: Settings,
    backend: str,
    split: str | None = None,
    model_name: str = REGISTERED,
    interpreter_kind: str = "model",
) -> dict:
    model_label = None
    if backend == "local":
        model, model_label = await resolve(settings, model_name)
        interpreter = ModelInterpreter(model, int(settings.model_timeout_seconds * 1000))
    else:
        interpreter = KeywordInterpreter()
    cases = {case.id: case for case in load_cases(settings.cases_path)}
    if interpreter_kind == "cascade":
        interpreter = build_cascade(settings, interpreter, cases)
    rows = []
    for label_set in load_labels():
        if split and label_set.split != split:
            continue
        case = cases[label_set.case_id]
        known = {fact.id for fact in case.facts}
        for item in label_set.items:
            unknown = set(item.expected) - known
            if unknown:
                raise ValueError(f"{case.id}: labels name unknown facts {sorted(unknown)}")
            history = (
                [(item.previous.interviewer, item.previous.character)] if item.previous else []
            )
            clock = perf_counter()
            interpretation, _, flags = await interpreter.interpret(
                case, DisclosureState(), history, item.utterance
            )
            rows.append(
                {
                    "case_id": case.id,
                    "split": label_set.split,
                    "utterance": item.utterance,
                    "expected": sorted(item.expected),
                    "selected": sorted(interpretation.asked),
                    "focus": interpretation.focus,
                    "topic_route": interpretation.topic_route,
                    "topic_leaning": interpretation.topic_leaning,
                    "tone_route": interpretation.tone_route,
                    "rapport": interpretation.rapport,
                    "expected_rapport": item.rapport,
                    "flags": flags,
                    "ms": round((perf_counter() - clock) * 1000),
                }
            )
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "interpreter": interpreter.id,
        "prompt_version": interpreter.prompt_version,
        "model": model_label,
        "summary": score(rows),
        "by_split": {
            split: score([r for r in rows if r["split"] == split])
            for split in SPLITS
            if any(r["split"] == split for r in rows)
        },
        "by_case": {
            case_id: score([r for r in rows if r["case_id"] == case_id])
            for case_id in dict.fromkeys(r["case_id"] for r in rows)
        },
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("fake", "local"), default=None)
    parser.add_argument("--split", choices=SPLITS, default=None)
    parser.add_argument("--model", default=REGISTERED, help="'registered' or an experiment id")
    parser.add_argument("--interpreter", choices=("model", "cascade"), default="cascade")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()
    settings = Settings()
    backend = args.backend or ("local" if args.model != REGISTERED else settings.model_backend)
    report = asyncio.run(evaluate(settings, backend, args.split, args.model, args.interpreter))
    for row in report["rows"]:
        if row["selected"] != row["expected"] or row["rapport"] != row["expected_rapport"]:
            print(
                f"MISS {row['case_id']}: {row['utterance']!r}\n"
                f"     expected={row['expected']} rapport={row['expected_rapport']} "
                f"selected={row['selected']} rapport={row['rapport']} focus={row['focus']!r}"
            )
    print(json.dumps({key: report[key] for key in ("by_split", "by_case")}, indent=2))
    if args.out:
        out = args.out if args.out.is_absolute() else ROOT / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
