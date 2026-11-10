"""Score student-interpreter predictions (from tools/finetune/predict.py).

Usage: npm run finetune:score -- RUN_DIR   # reads RUN_DIR/pred-*.jsonl, writes RUN_DIR/score.json

Topics: exact sets, spurious selections (each can unlock a hidden fact early) and misses.
Tone: empathy level and confrontation after the same deterministic quote rules as the
runtime. Invalid answers count as failures (at runtime they fall back to Qwen).
"""

import argparse
import json
import statistics
from pathlib import Path

from psychiatry_api.cases import load_cases
from psychiatry_api.finetune.format import parse, tone


def score_topics(rows, cases) -> dict:
    exact = spurious = missed = invalid = 0
    wrong = []
    for row in rows:
        meta = row["meta"]
        label = parse(cases[meta["case_id"]], row["output"])
        if label is None:
            invalid += 1
            wrong.append({"utterance": meta["utterance"], "output": row["output"][:200]})
            continue
        expected, chosen = set(meta["expected"]), set(label.asked)
        exact += chosen == expected
        spurious += len(chosen - expected)
        missed += len(expected - chosen)
        if chosen != expected:
            wrong.append(
                {
                    "utterance": meta["utterance"],
                    "expected": sorted(expected),
                    "chosen": sorted(chosen),
                }
            )
    return {
        "lines": len(rows),
        "exact": exact,
        "spurious": spurious,
        "missed": missed,
        "invalid": invalid,
        "wrong": wrong,
    }


def score_tone(rows, cases) -> dict:
    level = any_empathy = false_empathy = found = false_confront = invalid = 0
    for row in rows:
        meta = row["meta"]
        label = parse(cases[meta["case_id"]], row["output"])
        if label is None:
            invalid += 1
            continue
        empathy, confrontational = tone(label, meta["utterance"])
        level += empathy == meta["empathy"]
        any_empathy += (empathy > 0) == (meta["empathy"] > 0)
        false_empathy += empathy > 0 and meta["empathy"] == 0
        found += confrontational and meta["confrontational"]
        false_confront += confrontational and not meta["confrontational"]
    return {
        "lines": len(rows),
        "level_correct": level,
        "any_empathy_correct": any_empathy,
        "empathy_false_positives": false_empathy,
        "confrontation_found": found,
        "confrontation_expected": sum(r["meta"]["confrontational"] for r in rows),
        "confrontation_false_positives": false_confront,
        "invalid": invalid,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    args = parser.parse_args()
    cases = {case.id: case for case in load_cases()}
    result = {}
    for path in sorted(args.run.glob("pred-*.jsonl")):
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        name = path.stem.removeprefix("pred-")
        scored = score_tone(rows, cases) if name.endswith("tone") else score_topics(rows, cases)
        scored["median_ms"] = statistics.median(r["ms"] for r in rows)
        result[name] = scored
        print(name, {k: v for k, v in scored.items() if k != "wrong"})
    (args.run / "score.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
