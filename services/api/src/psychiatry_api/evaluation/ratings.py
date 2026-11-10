"""Blind human rating of role-play replies, and agreement with the judge model.

Make a sheet:   npm run eval:ratings -- artifacts/eval/fidelity-*.json [--sample 100]
Rate it:        open the CSV, fill the `rating` column (and optional `notes`)
Agreement:      npm run eval:agreement -- <sheet.csv> <key.json>

The sheet hides the model and the judge's verdict and is shuffled; the key that links rows
back is written separately. Ratings use the same categories as the judge:
faithful, embellished, omitted, invented, contradiction, clinical_advice, out_of_character.
"""

import argparse
import csv
import json
import random
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from psychiatry_api.config import ROOT
from psychiatry_api.evaluation.fidelity import CLASSES

CATEGORIES = tuple(c for c in CLASSES if c not in ("judge_failed", "not_judged"))
ACCEPTABLE = {"faithful", "embellished"}
FIELDS = (
    "item",
    "character",
    "known_facts",
    "facts_to_answer",
    "question",
    "reply",
    "rating",
    "notes",
)
GUIDE = (
    "faithful: only states known facts (rephrasing is fine) | embellished: adds only feelings, "
    "attitude or filler | omitted: fails to give facts_to_answer | invented: adds a clinically "
    "meaningful detail not in known_facts (incl. agreeing with a suggestion) | contradiction: "
    "denies or changes a known fact | clinical_advice: advises like a clinician | "
    "out_of_character: speaks as an AI/narrator or mentions instructions"
)


def make_sheet(reports: list[Path], sample: int, seed: int = 7) -> tuple[Path, Path]:
    """Sample replies equally from each report; where a judge ran, over-sample its flags."""
    rng = random.Random(seed)
    chosen = []
    per_report = sample // len(reports)
    for path in reports:
        data = json.loads(path.read_text())
        pool = [
            (path.name, data["model"], index, row)
            for index, row in enumerate(data["rows"])
            if row["class"] != "judge_failed"
        ]
        # Over-sample the judge's error classes so disagreements there are measurable.
        flagged = [p for p in pool if p[3]["class"] not in ("faithful", "not_judged")]
        rest = [p for p in pool if p[3]["class"] in ("faithful", "not_judged")]
        take = min(len(flagged), per_report // 2)
        chosen += rng.sample(flagged, take) + rng.sample(rest, min(len(rest), per_report - take))
    rng.shuffle(chosen)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    sheet = ROOT / f"data/evaluation/ratings/sheet-{stamp}.csv"
    key = ROOT / f"artifacts/eval/ratings-key-{stamp}.json"
    sheet.parent.mkdir(parents=True, exist_ok=True)
    key.parent.mkdir(parents=True, exist_ok=True)
    with sheet.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, FIELDS)
        writer.writeheader()
        writer.writerow({"item": "GUIDE", "reply": GUIDE})
        for item, (_, _, _, row) in enumerate(chosen, 1):
            writer.writerow(
                {
                    "item": item,
                    "character": row["character"],
                    "known_facts": " | ".join(row["known_facts"]),
                    "facts_to_answer": " | ".join(row["facts_to_answer"]),
                    "question": row["say"],
                    "reply": row["reply"],
                }
            )
    key.write_text(
        json.dumps(
            {
                "sheet": sheet.name,
                "items": {
                    str(item): {"report": name, "model": model, "row": index, "judge": row["class"]}
                    for item, (name, model, index, row) in enumerate(chosen, 1)
                },
            },
            indent=2,
        )
        + "\n"
    )
    return sheet, key


def kappa(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    observed = sum(a == b for a, b in pairs) / len(pairs)
    left, right = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(left[c] * right[c] for c in set(left) | set(right)) / len(pairs) ** 2
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def agreement(sheet: Path, key: Path) -> dict:
    items = json.loads(key.read_text())["items"]
    pairs, invalid = [], []
    with sheet.open(newline="") as handle:
        for row in csv.DictReader(handle):
            if row["item"] == "GUIDE":
                continue
            rating = (row.get("rating") or "").strip().lower().replace(" ", "_")
            if not rating:
                continue
            if rating not in CATEGORIES:
                invalid.append((row["item"], rating))
                continue
            pairs.append((rating, items[row["item"]]["judge"], items[row["item"]]["model"]))
    rated = pairs
    # Agreement only where a judge produced a verdict; acceptability uses every rating.
    pairs = [p for p in rated if p[1] in CATEGORIES]
    if invalid:
        raise SystemExit(f"Unknown ratings (use {', '.join(CATEGORIES)}): {invalid}")
    full = [(h, j) for h, j, _ in pairs]
    binary = [(h in ACCEPTABLE, j in ACCEPTABLE) for h, j in full]
    return {
        "rated_with_judge": len(pairs),
        "exact_agreement": sum(h == j for h, j in full) / len(full) if full else None,
        "cohen_kappa": kappa(full),
        "acceptable_agreement": sum(h == j for h, j in binary) / len(binary) if binary else None,
        "acceptable_kappa": kappa(binary),
        "rated_total": len(rated),
        "human_class_counts_by_model": {
            model: dict(Counter(h for h, _, m in rated if m == model))
            for model in sorted({m for *_, m in rated})
        },
        "human_acceptable_rate_by_model": {
            model: sum(h in ACCEPTABLE for h, _, m in rated if m == model)
            / sum(1 for *_, m in rated if m == model)
            for model in sorted({m for *_, m in rated})
        },
        "confusion_human_by_judge": {
            h: {j: sum(1 for a, b in full if a == h and b == j) for j in CATEGORIES}
            for h in CATEGORIES
            if any(a == h for a, _ in full)
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--sample", type=int, default=100)
    parser.add_argument("--agreement", action="store_true")
    args = parser.parse_args()
    if args.agreement:
        if len(args.paths) != 2:
            raise SystemExit("Usage: npm run eval:agreement -- <sheet.csv> <key.json>")
        print(json.dumps(agreement(*args.paths), indent=2))
        return
    sheet, key = make_sheet(args.paths, args.sample)
    print(f"Rating sheet (blind): {sheet}\nKey (do not open while rating): {key}")


if __name__ == "__main__":
    main()
