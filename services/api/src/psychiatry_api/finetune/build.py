"""Build the student interpreter's training and evaluation data.

Usage:
  npm run finetune:label    # Qwen3-4B (the teacher) labels what the authored data lacks
  npm run finetune:export   # write MLX chat files and evaluation sets to artifacts/finetune

Sources, each line with a topic label and a tone label:
- topic training lines (data/training/topics): authored topics; tone from the teacher;
- tone training lines (data/training/tone): authored tone; topics from the teacher;
- synthetic interviews with context (data/finetune/synthetic/*.yaml), when present:
  labels written with them;
- logged sessions (data/sessions, local only): turns whose topics Qwen decided, with the
  previous exchange. Split by session: one in three sessions is held out as a field test.
  These stay in artifacts/ and are never committed.

Evaluation items (data/evaluation) are never training data; the held-out test split is
exported only for the final run (--with-test).
"""

import argparse
import asyncio
import hashlib
import json
import random
from pathlib import Path

import yaml

from psychiatry_api.case_versions import write_manifest
from psychiatry_api.cases import CASES_PATH, Case, load_cases
from psychiatry_api.config import ROOT, Settings
from psychiatry_api.evaluation.interpreter import load_labels
from psychiatry_api.finetune.format import SYSTEM, Label, answer, render
from psychiatry_api.models.selection import language_model, verify_service
from psychiatry_api.roleplay.classify import challenge_text, statements
from psychiatry_api.roleplay.interpret import ModelInterpreter
from psychiatry_api.sources import UniqueKeyLoader

TRAINING = ROOT / "data/training"
TEACHER = ROOT / "data/finetune/teacher-labels.jsonl"
# Teacher labels for lines from real sessions: transcripts stay local, never committed.
TEACHER_LOCAL = ROOT / "artifacts/finetune/teacher-sessions.jsonl"
SYNTHETIC = ROOT / "data/finetune/synthetic"
OUT = ROOT / "artifacts/finetune/data"
CONFRONTATION_REPEATS = 4
# The runtime's rules leave a line with no statement and only information-seeking questions
# with no empathy and no confrontation, whatever a model says; no teacher call is needed.
RULED_TONE = {
    "empathy": "none",
    "empathy_words": "",
    "confrontational": False,
    "confrontational_words": "",
}


def line_id(case_id: str, utterance: str, previous: tuple[str, str] | None = None) -> str:
    text = json.dumps([case_id, " ".join(utterance.split()), previous])
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def authored() -> list[dict]:
    """Authored training lines, each with the half of its label that was written."""
    rows = []
    for path in sorted((TRAINING / "topics").glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        for item in data["items"]:
            # Follow-up lines carry the exchange they depend on.
            prev = item.get("previous")
            rows.append(
                {
                    "case_id": data["case_id"],
                    "utterance": item["utterance"],
                    "topics": sorted(item["topics"]),
                    "tone": None,
                    "source": path.name,
                    "previous": (prev["interviewer"], prev["character"]) if prev else None,
                }
            )
    for path in sorted((TRAINING / "tone").glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        for item in data["items"]:
            tone = {
                "empathy": ["none", "brief", "specific"][item["empathy"]],
                "empathy_words": item["empathy_words"],
                "confrontational": item["confrontational"],
                "confrontational_words": item["challenge_words"],
            }
            rows.append(
                {
                    "case_id": data["case_id"],
                    "utterance": item["utterance"],
                    "topics": None,
                    "tone": tone,
                    "source": path.name,
                }
            )
    return rows


def ruled(utterance: str) -> bool:
    return not statements(utterance) and not challenge_text(utterance)


def teacher_cache() -> dict[str, dict]:
    cache = {}
    for path in (TEACHER, TEACHER_LOCAL):
        if path.exists():
            cache.update({row["id"]: row for row in map(json.loads, path.read_text().splitlines())})
    return cache


async def label(limit: int | None = None) -> None:
    """Ask the teacher for each missing half; appends to the cache, so it can resume."""
    settings = Settings()
    await verify_service(settings)
    teacher = ModelInterpreter(language_model(settings), int(settings.model_timeout_seconds * 1000))
    cases = {case.id: case for case in load_cases(settings.cases_path)}
    cache = teacher_cache()
    # Logged training-split turns have Qwen's topics but no quoted tone words: ask for tone.
    session_train, _ = logged(settings.sessions_path)
    rows = authored() + [{**r, "topics": r["topics"], "tone": None} for r in session_train]
    todo, seen = [], set()
    for r in rows:
        ident = line_id(r["case_id"], r["utterance"])
        if ident not in cache and ident not in seen:
            seen.add(ident)
            todo.append(r)
    TEACHER.parent.mkdir(parents=True, exist_ok=True)
    TEACHER_LOCAL.parent.mkdir(parents=True, exist_ok=True)
    print(f"{len(todo)} lines to label ({len(cache)} cached)")
    with TEACHER.open("a") as shared, TEACHER_LOCAL.open("a") as local:
        for n, row in enumerate(todo[:limit] if limit else todo, 1):
            out = local if row["source"].startswith("session:") else shared
            case = cases[row["case_id"]]
            entry = {
                "id": line_id(row["case_id"], row["utterance"]),
                "case_id": row["case_id"],
                "utterance": row["utterance"],
                "teacher": "qwen3-4b",
            }
            if row["tone"] is None and ruled(row["utterance"]):
                entry |= {"teacher": "rules", "tone": RULED_TONE}
            elif row["tone"] is None:
                tone, _ = await teacher.tone(case, [], row["utterance"], None)
                if tone is None:
                    continue
                entry["tone"] = {
                    "empathy": tone.empathy,
                    "empathy_words": tone.empathy_words,
                    "confrontational": tone.confrontational,
                    "confrontational_words": tone.confrontational_words,
                }
            if row["topics"] is None:
                found, _, flags = await teacher.topics(case, [], row["utterance"])
                if flags:
                    continue
                entry["topics"] = sorted(found.asked)
            out.write(json.dumps(entry, ensure_ascii=False) + "\n")
            out.flush()
            if n % 50 == 0:
                print(f"  {n}/{len(todo)}")


def complete(rows: list[dict], cache: dict[str, dict]) -> list[dict]:
    done = []
    for row in rows:
        taught = cache.get(line_id(row["case_id"], row["utterance"]), {})
        topics = row["topics"] if row["topics"] is not None else taught.get("topics")
        tone = row["tone"] if row["tone"] is not None else taught.get("tone")
        if topics is not None and tone is not None:
            done.append({**row, "topics": topics, "tone": tone, "previous": row.get("previous")})
    return done


def synthetic() -> list[dict]:
    """Synthetic interviews (Prompt E). A line repeated with the same previous exchange is
    kept once: the drafts reuse stock phrases."""
    rows, seen = [], set()
    for path in sorted(SYNTHETIC.glob("*.yaml")) if SYNTHETIC.exists() else []:
        data = yaml.load(path.read_text(), Loader=UniqueKeyLoader)
        for interview in data["interviews"]:
            previous = None
            for turn in interview["turns"]:
                ident = line_id(data["case_id"], turn["doctor"], previous)
                if ident in seen:
                    previous = (turn["doctor"], turn["character"])
                    continue
                seen.add(ident)
                rows.append(
                    {
                        "case_id": data["case_id"],
                        "utterance": turn["doctor"],
                        "previous": previous,
                        "topics": sorted(turn["topics"]),
                        "tone": {
                            k: turn[k]
                            for k in (
                                "empathy",
                                "empathy_words",
                                "confrontational",
                                "confrontational_words",
                            )
                        },
                        "source": path.name,
                    }
                )
                previous = (turn["doctor"], turn["character"])
    return rows


def logged(sessions: Path) -> tuple[list[dict], list[dict]]:
    """(train, field test) from local-model sessions: Qwen-decided turns with context."""
    train, field = [], []
    for path in sorted(sessions.glob("*.jsonl")):
        events = [json.loads(line) for line in path.read_text().splitlines()]
        started = events[0]
        if started["backend"] != "local":
            continue
        qwen_only = started["interpreter"].startswith("model")
        held_out = int(hashlib.sha256(path.stem.encode()).hexdigest(), 16) % 3 == 0
        previous = None
        began = next((e for e in events if e["type"] == "began"), None)
        if began:
            previous = ("", began["opening"])
        for event in events:
            if event["type"] != "turn":
                continue
            if (qwen_only or event.get("topic_route") == "model") and event.get(
                "empathy"
            ) is not None:
                row = {
                    "case_id": started["case"]["id"],
                    "utterance": event["candidate"],
                    "previous": previous if previous and previous[0] else None,
                    "topics": sorted(event["asked"]),
                    "tone": None,
                    "logged_tone": (event["empathy"], event["confrontational"]),
                    "source": f"session:{path.stem[:8]}",
                }
                (field if held_out else train).append(row)
            previous = (event["candidate"], event["reply"])
    return train, field


def chat(case: Case, row: dict, target: str | None) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": render(case, row["utterance"], row.get("previous"))},
    ]
    if target is not None:
        messages.append({"role": "assistant", "content": target})
    return {"messages": messages}


def export(with_test: bool, with_synthetic: bool = True) -> None:
    cases = {case.id: case for case in load_cases()}
    cache = teacher_cache()
    session_train, session_field = logged(Settings().sessions_path)
    # Real transcripts (local only): Qwen's topics in context, the teacher's quoted tone.
    real = [
        {**r, "tone": cache.get(line_id(r["case_id"], r["utterance"]), {}).get("tone")}
        for r in session_train
    ]
    rows = complete(authored(), cache) + (synthetic() if with_synthetic else [])
    rows += [r for r in real if r["tone"]]
    random.Random(0).shuffle(rows)
    valid_n = max(20, len(rows) // 10)
    OUT.mkdir(parents=True, exist_ok=True)

    def target(row):
        tone = row["tone"]
        return answer(
            cases[row["case_id"]],
            Label(
                asked=frozenset(row["topics"]),
                empathy=tone["empathy"],
                empathy_words=tone["empathy_words"],
                confrontational=tone["confrontational"],
                confrontational_words=tone["confrontational_words"],
            ),
        )

    def write(name, items, with_target=True):
        with (OUT / name).open("w") as out:
            for row in items:
                record = chat(cases[row["case_id"]], row, target(row) if with_target else None)
                record["meta"] = {k: row.get(k) for k in ("case_id", "utterance", "source")}
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"{name}: {len(items)}")

    # Confrontation is rare (about 5% of lines): repeat those lines so the student does
    # not learn to answer "no" every time.
    train = rows[valid_n:]
    train += [r for r in train if r["tone"]["confrontational"]] * (CONFRONTATION_REPEATS - 1)
    random.Random(1).shuffle(train)
    write("train.jsonl", train)
    write("valid.jsonl", rows[:valid_n])
    # Record the case set this training data was built from; pin it with the model.
    write_manifest(CASES_PATH, OUT / "cases-manifest.json")

    # Evaluation sets carry gold labels in meta, not as targets.
    def eval_rows(split):
        items = []
        for labels in load_labels():
            if labels.split != split:
                continue
            for item in labels.items:
                prev = (
                    (item.previous.interviewer, item.previous.character) if item.previous else None
                )
                items.append(
                    {
                        "case_id": labels.case_id,
                        "utterance": item.utterance,
                        "previous": prev,
                        "expected": sorted(item.expected),
                    }
                )
        return items

    def write_eval(name, items):
        with (OUT / name).open("w") as out:
            for row in items:
                record = chat(cases[row["case_id"]], row, None)
                record["meta"] = {k: v for k, v in row.items() if k != "previous"}
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"{name}: {len(items)}")

    write_eval("dev-topics.jsonl", eval_rows("development"))
    rapport = yaml.load(
        (ROOT / "data/evaluation/rapport/development.yaml").read_text(), Loader=UniqueKeyLoader
    )["items"]
    write_eval(
        "dev-tone.jsonl",
        [
            {
                "case_id": i["case_id"],
                "utterance": i["utterance"],
                "previous": None,
                "empathy": i["empathy"],
                "confrontational": i["confrontational"],
            }
            for i in rapport
        ],
    )
    write_eval("field.jsonl", [{**r, "expected": r["topics"]} for r in session_field])
    if with_test:
        write_eval("test-topics.jsonl", eval_rows("test"))
    print(f"real session turns: {len(real)} for training, {len(session_field)} held out")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    labelling = sub.add_parser("label")
    labelling.add_argument("--limit", type=int)
    exporting = sub.add_parser("export")
    exporting.add_argument("--with-test", action="store_true")
    exporting.add_argument(
        "--without-synthetic", action="store_true", help="leave out data/finetune/synthetic"
    )
    args = parser.parse_args()
    if args.command == "label":
        asyncio.run(label(args.limit))
    else:
        export(args.with_test, with_synthetic=not args.without_synthetic)


if __name__ == "__main__":
    main()
