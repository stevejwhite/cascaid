"""How many real trainee lines the classifiers decide without Qwen, on logged sessions.

Usage: npm run eval:coverage -- [--sessions data/sessions] [--out artifacts/eval/coverage.json]

Every distinct candidate line in the session logs (local, not committed) is rated by the
classifiers trained on the current data/training. Reported per case and overall:

- topic_coverage: the share the topic classifier is confident about (no Qwen topic call);
- agreement_with_qwen: for lines Qwen labelled in the session (the topic route was the
  model), the share of the now-confident ones where the classifier gives Qwen's label.
  Qwen is not ground truth, but disagreement there flags labels to check;
- the lines still left to Qwen, to show what to cover next.

Needs the embedding server (npm run models:start). Lines are compared case-insensitively.
"""

import argparse
import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from psychiatry_api.cases import load_cases
from psychiatry_api.config import Settings
from psychiatry_api.models.selection import embedding_model
from psychiatry_api.roleplay.classify import TrainedClassifiers, classifier_cache, training_digest


def logged_lines(sessions: Path) -> list[dict]:
    """Distinct (case, line) pairs from local-model sessions, with Qwen's label when Qwen
    decided the topics (the cascade's model route, or the Qwen-only interpreter)."""
    seen: dict[tuple[str, str], dict] = {}
    for path in sorted(sessions.glob("*.jsonl")):
        case_id, qwen_only, local = None, False, False
        for raw in path.read_text().splitlines():
            event = json.loads(raw)
            if event["type"] == "started":
                case_id, local = event["case"]["id"], event["backend"] == "local"
                qwen_only = event["interpreter"].startswith("model")
            elif event["type"] == "turn" and local:
                key = (case_id, " ".join(event["candidate"].lower().split()))
                row = seen.setdefault(
                    key, {"case_id": case_id, "utterance": event["candidate"], "qwen": None}
                )
                if qwen_only or event.get("topic_route") == "model":
                    row["qwen"] = sorted(event["asked"])
    return list(seen.values())


async def run(sessions: Path) -> dict:
    settings = Settings()
    cases = {case.id: case for case in load_cases(settings.cases_path)}
    classifiers = TrainedClassifiers(embedding_model(settings), classifier_cache(settings))
    await classifiers.ready(cases)
    rows = []
    for line in logged_lines(sessions):
        case = cases.get(line["case_id"])
        if case is None:
            continue
        rating = await classifiers.rate(case, line["utterance"])
        topics = None if rating.topics is None else sorted(rating.topics)
        rows.append({**line, "classifier": topics, "confidence": rating.topic_confidence})

    def summary(selected: list[dict]) -> dict:
        confident = [r for r in selected if r["classifier"] is not None]
        compared = [r for r in confident if r["qwen"] is not None]
        return {
            "lines": len(selected),
            "topic_coverage": len(confident) / len(selected) if selected else None,
            "compared_with_qwen": len(compared),
            "agreement_with_qwen": (
                sum(r["classifier"] == r["qwen"] for r in compared) / len(compared)
                if compared
                else None
            ),
        }

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "training_digest": training_digest(),
        "overall": summary(rows),
        "by_case": {c: summary([r for r in rows if r["case_id"] == c]) for c in cases},
        "disagreements": [
            r
            for r in rows
            if r["classifier"] is not None and r["qwen"] not in (None, r["classifier"])
        ],
        "left_to_qwen": [
            {"case_id": r["case_id"], "utterance": r["utterance"], "confidence": r["confidence"]}
            for r in rows
            if r["classifier"] is None
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sessions", type=Path, default=Settings().sessions_path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    result = asyncio.run(run(args.sessions))
    print(json.dumps({"overall": result["overall"], "by_case": result["by_case"]}, indent=2))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
