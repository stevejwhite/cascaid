"""Reranker stage 1 (docs/RERANKER-PLAN.md): score labelled lines offline, then choose the
description, threshold and margin.

Usage:
  python -m psychiatry_api.evaluation.rerank score --description labels --split test --out S.json
  python -m psychiatry_api.evaluation.rerank analyse S.json [S2.json ...] \\
      --cascade RUN.json --qwen QWEN.json

score: every line of the split against every fact of its station (npm run reranker:start).
analyse: for a grid of thresholds and margins, the reranker alone (decided lines exact and
wrong releases; doubtful lines handed on) and a simulated cascade: the classifiers' decisions
(lines the --cascade run's classifiers decided), then the reranker under the cascade's rules
(form of the line, the classifier's leaning, the cross-check), then Qwen's decision from a
run where Qwen decided every line (--qwen). Results on the working set are post hoc.
"""

import argparse
import asyncio
import json
from pathlib import Path

from psychiatry_api.cases import load_cases
from psychiatry_api.config import Settings
from psychiatry_api.evaluation.interpreter import SPLITS, load_labels
from psychiatry_api.models.reranker import RerankerModel, running_reranker
from psychiatry_api.roleplay.classify import (
    NO_TOPIC,
    asks_question,
    compound,
    disagreement,
    rerank_inputs,
    reranked,
)

THRESHOLDS = (0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)
MARGINS = (0.0, 0.05, 0.1, 0.2, 0.3)


async def score(description: str, split: str, out: Path) -> None:
    settings = Settings()
    served = running_reranker(settings.reranker_state_file)
    if served is None:
        raise SystemExit("No topic reranker running: npm run reranker:start")
    model = RerankerModel(settings.reranker_base_url, served["model"], 60)
    cases = {case.id: case for case in load_cases(settings.cases_path)}
    rows = []
    for labels in load_labels():
        if labels.split != split:
            continue
        case = cases[labels.case_id]
        for item in labels.items:
            history = (
                [(item.previous.interviewer, item.previous.character)] if item.previous else []
            )
            instruction, query, documents = rerank_inputs(
                case, history, item.utterance, description
            )
            reply = await model.score(instruction, query, documents)
            rows.append(
                {
                    "case_id": case.id,
                    "utterance": item.utterance,
                    "expected": sorted(item.expected),
                    "scores": {f.id: s for f, s in zip(case.facts, reply.scores, strict=True)},
                    "ms": reply.total_ms,
                }
            )
    out.write_text(
        json.dumps(
            {"description": description, "split": split, "model": served, "rows": rows}, indent=1
        )
    )
    ms = sorted(r["ms"] for r in rows)
    print(f"{len(rows)} lines scored ({description}); median {ms[len(ms) // 2]} ms -> {out}")


def alone(rows, threshold, margin) -> dict:
    decided = exact = wrong = 0
    for row in rows:
        asked = reranked(row["scores"], threshold, margin)
        if asked is None:
            continue
        decided += 1
        exact += asked == set(row["expected"])
        wrong += bool(asked - set(row["expected"]))
    return {"decided": decided, "exact": exact, "wrong": wrong}


def simulate(rows, threshold, margin, cascade: dict, qwen: dict, cross_check: str) -> dict:
    exact = wrong = by_reranker = by_qwen = 0
    for row in rows:
        key = (row["case_id"], row["utterance"])
        run = cascade[key]
        if run["topic_route"] == "classifier":
            asked = set(run["selected"])
        else:
            asked = None
            if not compound(row["utterance"]):
                found = reranked(row["scores"], threshold, margin)
                question = asks_question(row["utterance"])
                leaning = run.get("topic_leaning")
                unsure = found is None or (
                    (bool(found) and not question)
                    or (not found and question and leaning != NO_TOPIC)
                )
                if not unsure and not disagreement(found, leaning, cross_check):
                    asked, by_reranker = set(found), by_reranker + 1
            if asked is None:
                asked, by_qwen = set(qwen.get(key, run)["selected"]), by_qwen + 1
        exact += asked == set(row["expected"])
        wrong += bool(asked - set(row["expected"]))
    return {"exact": exact, "wrong": wrong, "reranker": by_reranker, "qwen": by_qwen}


def analyse(paths: list[Path], cascade_path: Path, qwen_path: Path, cross_check: str) -> None:
    def rows_of(path):
        return {(r["case_id"], r["utterance"]): r for r in json.loads(path.read_text())["rows"]}

    cascade, qwen = rows_of(cascade_path), rows_of(qwen_path)
    qwen = {k: r for k, r in qwen.items() if r.get("topic_route") == "model"}
    reference = cascade.values()
    print(
        f"reference cascade ({cascade_path.name}): exact "
        f"{sum(set(r['selected']) == set(r['expected']) for r in reference)}, wrong "
        f"{sum(bool(set(r['selected']) - set(r['expected'])) for r in reference)} of {len(cascade)}"
    )
    for path in paths:
        data = json.loads(path.read_text())
        rows = [r for r in data["rows"] if (r["case_id"], r["utterance"]) in cascade]
        print(f"\n== {data['description']} ({len(rows)} lines)")
        print("   T     M  | alone: decided exact wrong | cascade: exact wrong reranker qwen")
        for threshold in THRESHOLDS:
            for margin in MARGINS:
                a = alone(rows, threshold, margin)
                c = simulate(rows, threshold, margin, cascade, qwen, cross_check)
                print(
                    f"  {threshold:.2f} {margin:.2f} | {a['decided']:5d} {a['exact']:5d} "
                    f"{a['wrong']:4d} | {c['exact']:5d} {c['wrong']:4d} {c['reranker']:5d} "
                    f"{c['qwen']:5d}"
                )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    scoring = sub.add_parser("score")
    scoring.add_argument("--description", choices=("labels", "labels_content"), required=True)
    scoring.add_argument("--split", choices=SPLITS, default="test")
    scoring.add_argument("--out", type=Path, required=True)
    analysing = sub.add_parser("analyse")
    analysing.add_argument("scores", type=Path, nargs="+")
    analysing.add_argument("--cascade", type=Path, required=True)
    analysing.add_argument("--qwen", type=Path, required=True)
    analysing.add_argument("--cross-check", choices=("off", "fact", "all"), default="all")
    args = parser.parse_args()
    if args.command == "score":
        asyncio.run(score(args.description, args.split, args.out))
    else:
        analyse(args.scores, args.cascade, args.qwen, args.cross_check)


if __name__ == "__main__":
    main()
