"""Compute feedback for saved session logs, for batch analysis.

Usage: npm run feedback -- data/sessions/<id>.jsonl [more.jsonl ...] [--summary]
"""

import argparse
import json
from pathlib import Path

from psychiatry_api.feedback.report import report
from psychiatry_api.roleplay.sessions import EVENT, Session


def load(path: Path) -> Session:
    return Session(
        [EVENT.validate_json(line) for line in path.read_text().splitlines() if line.strip()]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--summary", action="store_true", help="one line per session")
    args = parser.parse_args()
    for path in args.logs:
        session = load(path)
        if session.phase != "ended":
            print(f"{path.name}: skipped (station not ended)")
            continue
        feedback = report(session)
        if args.summary:
            info, comm = feedback.information, feedback.communication
            print(
                f"{path.name} {session.case.id}: key facts {info.key_elicited}/{info.key_total}, "
                f"{comm.utterances} utterances ({comm.open_questions} open, "
                f"{comm.closed_questions} closed), empathy {comm.empathy}, "
                f"summaries {comm.summaries}, "
                f"checks {comm.checks_of_understanding}, spoken {comm.spoken}"
            )
        else:
            print(
                json.dumps(
                    {"log": path.name, "case": session.case.id, **feedback.model_dump(mode="json")},
                    indent=2,
                )
            )


if __name__ == "__main__":
    main()
