"""Role-play fidelity, checklist accuracy and latency from scripted interviews.

Usage:
  npm run eval:fidelity -- [--model registered|<experiment id>] [--judge <experiment id>|registered]
                           [--cases a,b] [--out artifacts/eval/fidelity.json]

Every scripted interview (data/evaluation/scripts) runs through the real session pipeline.
Each reply gets deterministic checks and a judge-model verdict; each interview's feedback is
compared with the facts the script was designed to elicit. The judge is a model and can be
wrong: validate it against human ratings (npm run eval:ratings, npm run eval:agreement).
"""

import argparse
import asyncio
import json
import re
import statistics
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import yaml
from pydantic import Field

from psychiatry_api.cases import Case, load_cases
from psychiatry_api.config import ROOT, Settings
from psychiatry_api.domain import Contract
from psychiatry_api.evaluation.models import REGISTERED, resolve
from psychiatry_api.feedback.report import report
from psychiatry_api.models.contracts import (
    GenerationOptions,
    GenerationRequest,
    JsonOutput,
    LanguageModel,
    Message,
    ResponseFormat,
)
from psychiatry_api.models.errors import ModelError
from psychiatry_api.roleplay import sessions
from psychiatry_api.roleplay.classify import build_cascade
from psychiatry_api.roleplay.disclosure import DisclosureState, known
from psychiatry_api.roleplay.interpret import STOPWORDS, ModelInterpreter
from psychiatry_api.roleplay.respond import ModelRolePlayer, closing, numbers
from psychiatry_api.sources import UniqueKeyLoader

SCRIPTS = ROOT / "data/evaluation/scripts"
JUDGE_PROMPT = "fidelity-judge-v2"
Probe = Literal[
    "off_case",
    "leading",
    "break",
    "injection",
    "advice",
    "early_rapport",
    "repeat",
    "stacked",
    # Realism Phase 2.
    "follow_up",
    "rapport_level",
    "character_question",
    "answered",
    "affect",
]
PHASE_TWO = ("follow_up", "rapport_level", "character_question", "answered", "affect")
CLASSES = (
    "faithful",
    "embellished",
    "omitted",
    "invented",
    "contradiction",
    "clinical_advice",
    "out_of_character",
    "judge_failed",
    "not_judged",
)


class ScriptTurn(Contract):
    say: str
    expect: tuple[str, ...] = ()
    expect_deferred: tuple[str, ...] = ()
    expect_touched: tuple[str, ...] = ()
    expect_unlocked: tuple[str, ...] = ()
    expect_stage: str | None = None
    expect_question: str | None = None
    expect_answered: bool | None = None
    probe: Probe | None = None


class Interview(Contract):
    id: str
    kind: Literal["complete", "partial", "adversarial", "realism"]
    turns: tuple[ScriptTurn, ...]


class Script(Contract):
    case_id: str
    # The case version the items were written for; tests require it to match the case.
    case_version: str
    interviews: tuple[Interview, ...]


class Added(Contract):
    text: str = Field(max_length=160)
    significant: bool


class Verdict(Contract):
    added_details: tuple[Added, ...] = Field(max_length=6)
    contradicts_known_facts: bool
    answers_question: bool
    out_of_character: bool
    gives_clinical_advice: bool


def load_scripts(root: Path = SCRIPTS) -> tuple[Script, ...]:
    return tuple(
        Script.model_validate(yaml.load(path.read_text(), Loader=UniqueKeyLoader))
        for path in sorted(root.glob("*.yaml"))
    )


def content(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]+", text.lower()) if len(w) >= 5 and w not in STOPWORDS}


def possible_leaks(case: Case, state: DisclosureState, opening: str, said: str, reply: str):
    """Locked facts whose distinctive words appear in the reply (expected: none)."""
    allowed = content(
        " ".join(f.content for f in known(case, state))
        + f" {case.persona.description} {case.persona.speech_style} {opening} {said}"
    )
    heard = content(reply)
    leaks = []
    for fact in case.facts:
        if fact in known(case, state):
            continue
        distinctive = content(fact.content) - allowed
        if len(distinctive & heard) >= 2:
            leaks.append(fact.id)
    return leaks


async def judge(
    model: LanguageModel, case: Case, known_facts: list[str], to_answer: list[str], said, reply
):
    payload = {
        "character": {
            "name": case.persona.name,
            "role": case.persona.role,
            "age": case.persona.age,
            "background": case.persona.description,
        },
        "known_facts": known_facts,
        "facts_to_answer": to_answer,
        "question": said,
        "reply": reply,
    }
    request = GenerationRequest(
        messages=(
            Message(role="system", content=(ROOT / f"prompts/{JUDGE_PROMPT}.txt").read_text()),
            Message(role="user", content=json.dumps(payload, ensure_ascii=False)),
        ),
        options=GenerationOptions(
            prompt_version=JUDGE_PROMPT, max_output_tokens=400, temperature=0, seed=0
        ),
        response_format=ResponseFormat(
            type="json_schema", name="verdict", schema=Verdict.model_json_schema()
        ),
    )
    try:
        result = await model.generate(request)
    except ModelError:
        return None
    if not isinstance(result.output, JsonOutput):
        return None
    try:
        return Verdict.model_validate(result.output.value)
    except ValueError:
        return None


def corrected(
    verdict: Verdict | None, case: Case, known_facts: list[str], said: str
) -> Verdict | None:
    """Discard "added" details whose wording is mostly already in what the character knows.

    A deterministic guard against a known judge failure: listing known facts as additions.
    It only removes judge findings; the raw verdict is kept alongside for reporting.
    """
    if verdict is None:
        return None
    allowed = content(
        " ".join(known_facts)
        + f" {case.persona.description} {case.persona.opening_statement} {said}"
    )
    kept = []
    for added in verdict.added_details:
        words = content(added.text)
        if words and len(words & allowed) / len(words) >= 0.6:
            continue
        kept.append(added)
    return verdict.model_copy(update={"added_details": tuple(kept)})


def classify(verdict: Verdict | None, flags: tuple[str, ...], answering) -> str:
    if verdict is None:
        return "judge_failed"
    if verdict.out_of_character or "character_break" in flags:
        return "out_of_character"
    if verdict.gives_clinical_advice:
        return "clinical_advice"
    if verdict.contradicts_known_facts:
        return "contradiction"
    if any(a.significant for a in verdict.added_details):
        return "invented"
    if answering and not verdict.answers_question:
        return "omitted"
    if verdict.added_details:
        return "embellished"
    return "faithful"


def probe_passed(turn: ScriptTurn, row: dict) -> bool | None:
    if turn.probe is None:
        return None
    clean = row["class"] in ("faithful", "embellished") and not row["possible_leaks"]
    if turn.probe == "early_rapport":
        return (
            set(turn.expect_deferred) <= set(row["deferred"])
            and not row["unlocked"]
            and not row.get("touched")
        )
    if turn.probe in PHASE_TWO:
        # Every expectation the turn states must hold.
        return (
            set(turn.expect_deferred) <= set(row["deferred"])
            and set(turn.expect_touched) <= set(row["touched"])
            and set(turn.expect_unlocked) <= set(row["unlocked"])
            and (turn.expect_stage is None or row["affect_stage"] == turn.expect_stage)
            and (turn.expect_question is None or row["question"] == turn.expect_question)
            and (turn.expect_answered is None or row["answered"] == turn.expect_answered)
        )
    if turn.probe in ("repeat", "stacked"):
        return set(turn.expect) <= set(row["answering"]) and row["class"] != "contradiction"
    return clean


def percentile(values: list[int], q: float) -> int | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(q * (len(ordered) - 1)))]


def timing(rows: list[dict], key: str) -> dict:
    values = [r[key] for r in rows if r.get(key) is not None]
    return {"median": percentile(values, 0.5), "p95": percentile(values, 0.95), "n": len(values)}


def resident_mb() -> dict:
    """Resident memory of the local model servers that are running now."""
    pids = {}
    for name, path, key in (
        ("generation", "runtime-state.json", None),
        ("embedding", "runtime-state.json", None),
        ("experiment", "experiment-state.json", "server_pid"),
        ("speech", "speech-state.json", "server_pid"),
    ):
        try:
            state = json.loads((ROOT / "artifacts/m4" / path).read_text())
        except (OSError, ValueError):
            continue
        pid = (
            state.get(key)
            if key
            else next((p["pid"] for p in state.get("processes", []) if p["kind"] == name), None)
        )
        if pid:
            pids[name] = pid
    sizes = {}
    for name, pid in pids.items():
        out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True)
        if not out.stdout.strip():
            continue
        # RSS counts the memory-mapped model file but misses Metal buffers; macOS's
        # footprint counts private and GPU memory but not the mapped file. Report both.
        entry = {"rss_mb": round(int(out.stdout.strip()) / 1024)}
        foot = subprocess.run(["footprint", "-p", str(pid)], capture_output=True, text=True)
        match = re.search(r"phys_footprint:\s+([\d.]+)\s*([KMG]B)", foot.stdout)
        if match:
            scale = {"KB": 1 / 1024, "MB": 1, "GB": 1024}[match.group(2)]
            entry["footprint_mb"] = round(float(match.group(1)) * scale)
        sizes[name] = entry
    return sizes


def checklist(case: Case, interview: Interview, session) -> dict:
    feedback = report(session)
    scored = [f for f in case.facts if f.key and f.disclosure != "volunteered"]
    expected = {i for t in interview.turns for i in t.expect} & {f.id for f in scored}
    # A fact touched on (vague version only) was still asked about: the checklist measures
    # whether feedback records what the candidate asked. Full detail is reported separately.
    found = {"elicited", "touched_on"}
    actual = {f.id for f in feedback.information.facts if f.status in found} & {
        f.id for f in scored
    }
    return {
        "key_facts": len(scored),
        "expected_elicited": sorted(expected),
        "reported_elicited": sorted(actual),
        "true_positive": len(expected & actual),
        "false_positive": len(actual - expected),
        "false_negative": len(expected - actual),
        "correct_status": sum((f.id in expected) == (f.id in actual) for f in scored),
        "touched_on": sorted(
            f.id for f in feedback.information.facts if f.status == "touched_on" and f.key
        ),
    }


async def run(
    settings: Settings,
    model_name: str,
    judge_name: str,
    case_ids,
    out_dir: Path,
    condition: str = "gated",
    interpreter_kind: str = "model",
):
    model, model_label = await resolve(settings, model_name)
    # "none" skips judging: a clean latency run loads only the deployed models.
    judge_model, judge_label = (
        (None, "none") if judge_name == "none" else await resolve(settings, judge_name)
    )
    timeout_ms = int(settings.model_timeout_seconds * 1000)
    if condition == "full-case":
        # Baseline: the whole case in one prompt, withheld by instruction only.
        from psychiatry_api.evaluation.baseline import FullCaseRolePlayer, NullInterpreter

        interpreter, player = NullInterpreter(), FullCaseRolePlayer(model, timeout_ms)
    else:
        interpreter = ModelInterpreter(model, timeout_ms)
        player = ModelRolePlayer(model, timeout_ms)
    cases = {c.id: c for c in load_cases(settings.cases_path)}
    if interpreter_kind == "cascade":
        interpreter = build_cascade(settings, interpreter, cases)
    store = sessions.SessionStore(out_dir / "sessions")
    rows, interviews = [], []
    for script in load_scripts():
        if case_ids and script.case_id not in case_ids:
            continue
        case = cases[script.case_id]
        for interview in script.interviews:
            session = sessions.begin(
                store, sessions.create(store, settings, case, interpreter, player)
            )
            opening = case.persona.opening_statement
            for number, turn in enumerate(interview.turns, 1):
                session = await sessions.take_turn(store, session, turn.say, interpreter, player)
                logged = session.turns[-1]
                state = session.state()
                known_facts = [f.content for f in known(case, state)]
                to_answer = [f.content for f in case.facts if f.id in logged.answering]
                raw = (
                    await judge(judge_model, case, known_facts, to_answer, turn.say, logged.reply)
                    if judge_model
                    else None
                )
                verdict = corrected(raw, case, known_facts, turn.say)
                stated = numbers(
                    " ".join(f.content for f in known(case, state))
                    + f" {case.persona.description} {opening} {turn.say} {case.persona.age or ''}"
                )
                row = {
                    "case_id": case.id,
                    "interview": interview.id,
                    "kind": interview.kind,
                    "turn": number,
                    "probe": turn.probe,
                    "say": turn.say,
                    "reply": logged.reply,
                    "character": f"{case.persona.name} ({case.persona.role}): "
                    f"{case.persona.description}",
                    "known_facts": [f.content for f in known(case, state)],
                    "facts_to_answer": [f.content for f in case.facts if f.id in logged.answering],
                    "expect": sorted(turn.expect),
                    "expect_deferred": sorted(turn.expect_deferred),
                    "answering": list(logged.answering),
                    "unlocked": list(logged.unlocked),
                    "deferred": list(logged.deferred),
                    "touched": list(logged.touched),
                    "empathy": logged.empathy,
                    "confrontational": logged.confrontational,
                    "rapport_level": logged.rapport_level,
                    "affect_stage": logged.affect_stage,
                    "question": logged.question,
                    "answered": logged.answered,
                    "interpretation_correct": set(logged.answering) == set(turn.expect)
                    and set(turn.expect_deferred) <= set(logged.deferred),
                    "flags": list(logged.flags),
                    "unsupported_numbers": sorted(numbers(logged.reply) - stated),
                    "possible_leaks": possible_leaks(case, state, opening, turn.say, logged.reply),
                    "verdict": verdict.model_dump() if verdict else None,
                    "raw_verdict": raw.model_dump() if raw else None,
                    "interpret_ms": logged.interpret_ms,
                    "respond_ms": logged.respond_ms,
                    "first_token_ms": logged.calls[-1].first_token_ms if logged.calls else None,
                    "first_sentence_ms": logged.first_sentence_ms,
                    "topic_route": logged.topic_route,
                    "topic_confidence": logged.topic_confidence,
                    "tone_route": logged.tone_route,
                    "tone_confidence": logged.tone_confidence,
                    "calls": [call.model_dump() for call in logged.calls],
                    "turn_ms": logged.total_ms,
                }
                row["class"] = (
                    classify(verdict, logged.flags, logged.answering)
                    if judge_model
                    else "not_judged"
                )
                row["probe_passed"] = probe_passed(turn, row)
                rows.append(row)
                probe = ""
                if turn.probe:
                    probe = f" probe {turn.probe}: {'pass' if row['probe_passed'] else 'FAIL'}"
                print(
                    f"[{case.id}/{interview.id} {number}] {row['class']}{probe}: "
                    f"{logged.reply[:90]!r}",
                    flush=True,
                )
            session = sessions.end(store, session)
            interviews.append(
                {
                    "case_id": case.id,
                    "interview": interview.id,
                    "kind": interview.kind,
                    **checklist(case, interview, session),
                }
            )
    return summarise(rows, interviews) | {
        "generated_at": datetime.now(UTC).isoformat(),
        "model": model_label,
        "judge": judge_label,
        "judge_prompt": JUDGE_PROMPT,
        "condition": condition,
        "interpreter": interpreter.id,
        "interpreter_prompt": interpreter.prompt_version,
        "classifier_routes": {
            part: sum(r[f"{part}_route"] == "classifier" for r in rows) / len(rows)
            for part in ("topic", "tone")
        },
        "resident_memory_mb": resident_mb(),
        "rows": rows,
        "interviews": interviews,
    }


async def rejudge(settings: Settings, path: Path, judge_name: str) -> dict:
    """Re-score an existing report's replies with another judge; replies are unchanged."""
    data = json.loads(path.read_text())
    judge_model, judge_label = await resolve(settings, judge_name)
    cases = {c.id: c for c in load_cases(settings.cases_path)}
    rows = []
    for row in data["rows"]:
        case = cases[row["case_id"]]
        raw = await judge(
            judge_model, case, row["known_facts"], row["facts_to_answer"], row["say"], row["reply"]
        )
        verdict = corrected(raw, case, row["known_facts"], row["say"])
        turn = ScriptTurn(
            say=row["say"],
            expect=tuple(row["expect"]),
            expect_deferred=tuple(row["expect_deferred"]),
            probe=row["probe"],
        )
        updated = row | {
            "verdict": verdict.model_dump() if verdict else None,
            "raw_verdict": raw.model_dump() if raw else None,
            "class": classify(verdict, tuple(row["flags"]), row["answering"]),
        }
        # Phase 2 probes check logged behaviour, not the judge, so they carry over.
        if row["probe"] not in PHASE_TWO:
            updated["probe_passed"] = probe_passed(turn, updated)
        rows.append(updated)
        print(f"[{row['case_id']}/{row['interview']} {row['turn']}] {updated['class']}", flush=True)
    return (
        data
        | summarise(rows, data["interviews"])
        | {
            "judge": judge_label,
            "rejudged_from": path.name,
            "generated_at": datetime.now(UTC).isoformat(),
            "rows": rows,
        }
    )


def repeated_closings(rows: list[dict]) -> int:
    """Replies ending with a sentence the character already used in the same interview."""
    seen, repeats = {}, 0
    for row in rows:
        end = re.sub(r"[^a-z ]", "", closing(row["reply"]).lower()).strip()
        earlier = seen.setdefault((row["case_id"], row["interview"]), set())
        repeats += end in earlier
        earlier.add(end)
    return repeats


def calls_by_prompt(rows: list[dict]) -> dict:
    """Per prompt version: call count, and median input, cached-input and output tokens,
    prompt-processing time and total time."""
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        for call in row.get("calls", []):
            grouped.setdefault(call["prompt_version"], []).append(call)

    def median(calls, key):
        values = [c[key] for c in calls if c.get(key) is not None]
        return statistics.median(values) if values else None

    return {
        prompt: {
            "calls": len(calls),
            **{
                key: median(calls, key)
                for key in (
                    "input_tokens",
                    "cached_input_tokens",
                    "output_tokens",
                    "prompt_ms",
                    "first_token_ms",
                    "total_ms",
                )
            },
        }
        for prompt, calls in sorted(grouped.items())
    }


def summarise(rows: list[dict], interviews: list[dict]) -> dict:
    counts = {c: sum(r["class"] == c for r in rows) for c in CLASSES}
    probes = {}
    for r in rows:
        if r["probe"]:
            passed, total = probes.get(r["probe"], (0, 0))
            probes[r["probe"]] = (passed + bool(r["probe_passed"]), total + 1)
    tp = sum(i["true_positive"] for i in interviews)
    fp = sum(i["false_positive"] for i in interviews)
    fn = sum(i["false_negative"] for i in interviews)
    judged = len(rows) - counts["judge_failed"] - counts["not_judged"]
    return {
        "turns": len(rows),
        "fidelity": counts,
        "faithful_or_embellished": (counts["faithful"] + counts["embellished"]) / judged
        if judged
        else None,
        "serious_errors": sum(
            counts[c] for c in ("invented", "contradiction", "clinical_advice", "out_of_character")
        ),
        "possible_leaks": sum(bool(r["possible_leaks"]) for r in rows),
        "unsupported_numbers": sum(bool(r["unsupported_numbers"]) for r in rows),
        "interpretation_correct": sum(r["interpretation_correct"] for r in rows) / len(rows),
        "repeated_closings": repeated_closings(rows) / len(rows),
        "probes": {k: {"passed": p, "total": t} for k, (p, t) in sorted(probes.items())},
        "checklist": {
            "precision": tp / (tp + fp) if tp + fp else None,
            "recall": tp / (tp + fn) if tp + fn else None,
            "fact_status_accuracy": sum(i["correct_status"] for i in interviews)
            / max(1, sum(i["key_facts"] for i in interviews)),
        },
        "latency_ms": {
            "interpret": timing(rows, "interpret_ms"),
            "respond": timing(rows, "respond_ms"),
            "respond_first_token": timing(rows, "first_token_ms"),
            "first_sentence": timing(rows, "first_sentence_ms"),
            "turn": timing(rows, "turn_ms"),
        },
        "calls_by_prompt": calls_by_prompt(rows),
        "median_turn_seconds_by_kind": {
            kind: (statistics.median([r["turn_ms"] for r in rows if r["kind"] == kind]) / 1000)
            for kind in ("complete", "partial", "adversarial", "realism")
            if any(r["kind"] == kind for r in rows)
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--model", default=REGISTERED)
    parser.add_argument("--judge", default="qwen3-8b-q4-k-m")
    parser.add_argument("--cases", default="")
    parser.add_argument("--rejudge", type=Path, help="re-score this report's replies only")
    parser.add_argument(
        "--condition",
        choices=("gated", "full-case"),
        default="gated",
        help="full-case: baseline with the whole case in the prompt and no gating",
    )
    parser.add_argument(
        "--interpreter",
        choices=("model", "cascade"),
        default="cascade",
        help="cascade (default): local classifiers first, the Qwen interpreter when not "
        "confident; model: the Qwen interpreter on every turn",
    )
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.rejudge:
        result = asyncio.run(rejudge(Settings(), args.rejudge, args.judge))
    else:
        out_dir = Path(tempfile.mkdtemp(prefix="fidelity-", dir=ROOT / "artifacts"))
        cases = {c for c in args.cases.split(",") if c}
        result = asyncio.run(
            run(
                Settings(),
                args.model,
                args.judge,
                cases,
                out_dir,
                args.condition,
                args.interpreter,
            )
        )
        result["sessions_dir"] = str(out_dir / "sessions")
    summary = {k: v for k, v in result.items() if k not in ("rows", "interviews")}
    print(json.dumps(summary, indent=2))
    if args.out:
        out = args.out if args.out.is_absolute() else ROOT / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
