"""Compare early disclosure across conditions, using each script's design as ground truth.

Usage: npm run eval:leaks -- artifacts/eval/fidelity-a.json artifacts/eval/fidelity-b.json

A fact is *allowed* at a turn if it is volunteered or the script expected it at that turn
or earlier. A reply is flagged when it carries two or more distinctive word stems (or a
number) found only in a not-yet-allowed fact. Flags are a screen for manual review, not a
verdict: confirm each flagged reply by reading it.
"""

import argparse
import json
import re
from pathlib import Path

from psychiatry_api.cases import Case, load_cases
from psychiatry_api.evaluation.fidelity import load_scripts
from psychiatry_api.roleplay.respond import NUMBER_WORDS

# Everyday words that carry no case content; extends the earlier >=5-letter rule, which
# flagged replies for sharing words such as "think" and "really" with a locked fact.
COMMON = frozenset(
    """about above after again against always another around because before being below
    between bring could didn't doesn't don't every going gonna haven't having maybe might
    never other people really right should something sometimes still their there these
    thing things think those though through today under until wanna wasn't where which
    while worried worry would years yeah you're yourself honest honestly little sure
    actually anything everything nothing someone everyone trying though pretty since start
    started feeling feels thanks thank sorry talking talk""".split()
)


def stems(text: str) -> set[str]:
    words = re.findall(r"[a-z']+", text.lower())
    found = {w[:5] for w in words if len(w) >= 5 and w not in COMMON}
    found |= {f"#{n}" for n in re.findall(r"\d+", text)}
    found |= {f"#{NUMBER_WORDS[w]}" for w in words if w in NUMBER_WORDS and w != "one"}
    return found


def flags(case: Case, allowed: set[str], said: str, reply: str) -> list[str]:
    persona = case.persona
    context = stems(
        f"{persona.description} {persona.speech_style} {persona.affect} "
        f"{persona.opening_statement} {case.unscripted_response} {said} "
        + " ".join(f.content for f in case.facts if f.id in allowed)
    )
    heard = stems(reply)
    leaked = []
    for fact in case.facts:
        if fact.id in allowed:
            continue
        distinctive = stems(fact.content) - context
        hits = distinctive & heard
        if len(hits) >= 2 or any(h.startswith("#") for h in hits):
            leaked.append(fact.id)
    return leaked


def analyse(path: Path) -> dict:
    data = json.loads(path.read_text())
    cases = {c.id: c for c in load_cases()}
    expected = {
        (s.case_id, i.id): [set(t.expect) for t in i.turns]
        for s in load_scripts()
        for i in s.interviews
    }
    rows = []
    for row in data["rows"]:
        case = cases[row["case_id"]]
        so_far = expected[(row["case_id"], row["interview"])][: row["turn"]]
        allowed = {f.id for f in case.facts if f.disclosure == "volunteered"}.union(*so_far)
        leaked = flags(case, allowed, row["say"], row["reply"])
        rows.append(
            {k: row[k] for k in ("case_id", "interview", "turn", "probe", "say", "reply")}
            | {"flagged": leaked}
        )
    flagged = [r for r in rows if r["flagged"]]
    return {
        "report": path.name,
        "model": data["model"],
        "condition": data.get("condition", "gated"),
        "turns": len(rows),
        "flagged_turns": len(flagged),
        "flagged_by_probe": {
            p: sum(1 for r in flagged if r["probe"] == p)
            for p in sorted({r["probe"] or "none" for r in rows})
        }
        | {"none": sum(1 for r in flagged if not r["probe"])},
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("reports", nargs="+", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    results = [analyse(path) for path in args.reports]
    for result in results:
        print(
            f"\n== {result['report']} ({result['condition']}, {result['model']}): "
            f"{result['flagged_turns']}/{result['turns']} turns flagged"
        )
        for r in result["rows"]:
            if r["flagged"]:
                print(
                    f"  [{r['case_id']}/{r['interview']} {r['turn']} {r['probe'] or ''}] "
                    f"{r['flagged']}\n     Q: {r['say']}\n     A: {r['reply']}"
                )
    if args.out:
        args.out.write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
