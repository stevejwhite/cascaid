"""Phase 2c: offline evaluation of classifier interpretation (development data only).

Usage: npm run eval:classifier -- [--out artifacts/eval/classifier-dev.json]

Trains topic and tone classifiers on data/training/: logistic regression on the local
embedding model's vectors plus word and character n-gram features (embeddings alone or
word features alone did worse; see docs/QWEN-SPECIFICATION.md). Accept-or-defer
thresholds are picked on out-of-fold training predictions, then measured on the
development label sets. A deferred line goes to the Qwen interpreter; its recorded
development results stand in for those calls. The held-out test sets are not read.
"""

import argparse
import asyncio
import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import yaml
from sklearn.model_selection import KFold

from psychiatry_api.cases import load_cases
from psychiatry_api.config import ROOT, Settings
from psychiatry_api.models.selection import embedding_model, verify_embedding_service
from psychiatry_api.roleplay.classify import (
    EMBEDDING_WEIGHT,
    TOPIC_C,
    Classifier,
    Embedder,
    ToneHeads,
    ToneItem,
    TopicItem,
    challenge_text,
    classifier_cache,
    decide,
    label_of,
    statements,
    tone_training,
    topic_training,
)
from psychiatry_api.roleplay.classify import NO_TOPIC as NONE
from psychiatry_api.roleplay.classify import fit_tone as fit_tone_heads
from psychiatry_api.roleplay.interpret import SPECIFIC_MIN_WORDS

EVALUATION = ROOT / "data/evaluation"
# Recorded Qwen results on the development sets, used for deferred lines.
QWEN_TOPICS = ROOT / "artifacts/eval/interpreter-reuse-dev.json"
QWEN_TONE = ROOT / "artifacts/eval/rapport-v2-dev.json"


# ---------------------------------------------------------------------------------- data
def load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def topic_development() -> list[TopicItem]:
    items = []
    for path in sorted((EVALUATION / "interpreter").glob("*.yaml")):
        data = load_yaml(path)
        if data["split"] != "development":
            continue
        for item in data["items"]:
            items.append(TopicItem(data["case_id"], item["utterance"], frozenset(item["expected"])))
    return items


def tone_development() -> list[ToneItem]:
    data = load_yaml(EVALUATION / "rapport/development.yaml")
    return [
        ToneItem(i["case_id"], i["utterance"], i["empathy"], i["confrontational"])
        for i in data["items"]
    ]


# ------------------------------------------------------------------------------ topics
def topic_outcomes(rows, threshold: float):
    accepted = correct = spurious = 0
    for item, label, confidence in rows:
        chosen = decide(item.utterance, label, confidence, threshold)
        if chosen is None:
            continue
        accepted += 1
        correct += chosen == item.topics
        spurious += len(chosen - item.topics)
    return accepted, correct, spurious


THRESHOLDS = (0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.98)


def pick_threshold(rows) -> float:
    """Most coverage with at least 98.5% exact match among accepted lines (the Qwen topic
    call's held-out level)."""
    best = (0, 0.99)
    for threshold in THRESHOLDS:
        accepted, correct, _ = topic_outcomes(rows, threshold)
        if accepted and correct / accepted >= 0.985 and accepted > best[0]:
            best = (accepted, threshold)
    return best[1]


async def per_case_topics(embedder, cases, training, development):
    """One classifier per case over its facts plus "none", trained on single-topic and
    no-topic lines and the facts' own labels. Two-question lines are left to Qwen."""
    out_of_fold, dev_rows = [], []
    by_case = defaultdict(list)
    for item in training:
        if len(item.topics) <= 1:
            by_case[item.case_id].append(item)
    for case_id, items in by_case.items():
        case = cases[case_id]
        extra = [
            TopicItem(case_id, label, frozenset({f.id}))
            for f in case.facts
            for label in f.asked_about
        ]
        texts, extra_texts = [i.utterance for i in items], [i.utterance for i in extra]
        x, xe = (
            await embedder.embed(texts),
            await embedder.embed(extra_texts),
        )
        labels, extra_labels = [label_of(i) for i in items], [label_of(i) for i in extra]
        for train, test in KFold(n_splits=5, shuffle=True, random_state=0).split(x):
            model = Classifier(TOPIC_C).fit(
                [texts[i] for i in train] + extra_texts,
                np.vstack([x[train], xe]),
                [labels[i] for i in train] + extra_labels,
            )
            for i, (label, confidence) in zip(
                test, model.predict([texts[i] for i in test], x[test]), strict=True
            ):
                out_of_fold.append((items[i], label, confidence))
        model = Classifier(TOPIC_C).fit(
            texts + extra_texts, np.vstack([x, xe]), labels + extra_labels
        )
        dev_items = [i for i in development if i.case_id == case_id]
        if dev_items:
            dev_texts = [i.utterance for i in dev_items]
            predictions = model.predict(dev_texts, await embedder.embed(dev_texts))
            dev_rows += [
                (i, label, conf) for i, (label, conf) in zip(dev_items, predictions, strict=True)
            ]
    return out_of_fold, dev_rows


# ----------------------------------------------------------------------------- tone heads
async def fit_tone(embedder, items: list[ToneItem]) -> ToneHeads:
    said = await embedder.embed([statements(i.utterance) for i in items if statements(i.utterance)])
    challenge = await embedder.embed(
        [challenge_text(i.utterance) for i in items if challenge_text(i.utterance)]
    )
    return fit_tone_heads(items, said, challenge)


async def rate_tone(embedder, heads: ToneHeads, items: list[ToneItem]):
    """(item, empathy, confidence, confrontational, confidence) per line, with the runtime's
    rules applied: no statement means no empathy, no challenging sentence means no
    confrontation (both certain), and a short 'specific' becomes brief."""
    rows = []
    for item in items:
        said, challenge = statements(item.utterance), challenge_text(item.utterance)
        if said:
            [(level, e_conf)] = heads.empathy.predict([said], await embedder.embed([said]))
            level = int(level)
            if level == 2 and len(said.split()) < SPECIFIC_MIN_WORDS:
                level = 1
        else:
            level, e_conf = 0, 1.0
        if challenge:
            [(confront, c_conf)] = heads.confrontation.predict(
                [challenge], await embedder.embed([challenge])
            )
            confront = bool(confront)
        else:
            confront, c_conf = False, 1.0
        rows.append((item, level, e_conf, confront, c_conf))
    return rows


def tone_outcomes(rows, threshold: float):
    accepted = [r for r in rows if r[2] >= threshold and r[4] >= threshold]
    if not accepted:
        return {"accepted": 0}
    return {
        "accepted": len(accepted),
        "any_empathy_correct": sum((r[1] > 0) == (r[0].empathy > 0) for r in accepted),
        "empathy_false_positives": sum(r[1] > 0 and r[0].empathy == 0 for r in accepted),
        "level_correct": sum(r[1] == r[0].empathy for r in accepted),
        "confrontation_correct": sum(r[3] == r[0].confrontational for r in accepted),
        "confrontation_false_positives": sum(r[3] and not r[0].confrontational for r in accepted),
        "confrontation_missed": sum(not r[3] and r[0].confrontational for r in accepted),
    }


def pick_tone_threshold(rows) -> float:
    """Most coverage with no false empathy, at least 90% level accuracy and no false
    confrontation among accepted lines."""
    best = (0, 0.99)
    for threshold in (0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.98):
        o = tone_outcomes(rows, threshold)
        if not o["accepted"]:
            continue
        if (
            o["empathy_false_positives"] == 0
            and o["confrontation_false_positives"] == 0
            and o["level_correct"] / o["accepted"] >= 0.9
            and o["accepted"] > best[0]
        ):
            best = (o["accepted"], threshold)
    return best[1]


async def tone_out_of_fold(embedder, items: list[ToneItem]):
    rows = []
    folds = KFold(n_splits=5, shuffle=True, random_state=0)
    for train_index, test_index in folds.split(items):
        heads = await fit_tone(embedder, [items[i] for i in train_index])
        rows += await rate_tone(embedder, heads, [items[i] for i in test_index])
    return rows


# ------------------------------------------------------------------------------- report
def qwen_topics() -> dict[str, frozenset[str]]:
    if not QWEN_TOPICS.exists():
        return {}
    rows = json.loads(QWEN_TOPICS.read_text())["rows"]
    return {r["utterance"]: frozenset(r["selected"]) for r in rows if r["split"] == "development"}


def qwen_tone() -> dict[str, tuple[int, bool]]:
    if not QWEN_TONE.exists():
        return {}
    rows = json.loads(QWEN_TONE.read_text())["rows"]
    return {r["utterance"]: (r["rated"], bool(r["rated_confrontational"])) for r in rows}


def topic_report(out_of_fold, dev_rows, qwen):
    threshold = pick_threshold(out_of_fold)
    accepted, correct, spurious = topic_outcomes(out_of_fold, threshold)
    dev = []
    for item, label, confidence in dev_rows:
        chosen = decide(item.utterance, label, confidence, threshold)
        fallback = qwen.get(item.utterance)
        final = chosen if chosen is not None else fallback
        dev.append(
            {
                "case_id": item.case_id,
                "utterance": item.utterance,
                "expected": sorted(item.topics),
                "classifier": None if chosen is None else sorted(chosen),
                "best_guess": [label, round(confidence, 3)],
                "qwen": None if fallback is None else sorted(fallback),
                "cascade": None if final is None else sorted(final),
            }
        )
    decided = [r for r in dev if r["classifier"] is not None]
    cascade = [r for r in dev if r["cascade"] is not None]
    qwen_rows = [r for r in dev if r["qwen"] is not None]

    def spurious_of(rows, key):
        return sum(len(set(r[key]) - set(r["expected"])) for r in rows)

    by_threshold = []
    for t in THRESHOLDS:
        a, c, sp = topic_outcomes(out_of_fold, t)
        d = [(i, lab, conf) for i, lab, conf in dev_rows]
        da, dc, dsp = topic_outcomes(d, t)
        by_threshold.append(
            {
                "threshold": t,
                "training_coverage": round(a / len(out_of_fold), 3),
                "training_accepted_exact": round(c / a, 4) if a else None,
                "training_spurious": sp,
                "development_decided": da,
                "development_exact": dc,
                "development_spurious": dsp,
            }
        )
    return {
        "threshold": threshold,
        "by_threshold": by_threshold,
        "training_out_of_fold": {
            "lines": len(out_of_fold),
            "first_choice_correct": sum(
                (frozenset() if label == NONE else frozenset({label})) == item.topics
                for item, label, _ in out_of_fold
            )
            / len(out_of_fold),
            "coverage": accepted / len(out_of_fold),
            "accepted_exact": correct / accepted if accepted else None,
            "accepted_spurious": spurious,
        },
        "development": {
            "lines": len(dev),
            "classifier_decides": len(decided),
            "classifier_exact": sum(r["classifier"] == r["expected"] for r in decided),
            "classifier_spurious": spurious_of(decided, "classifier"),
            "cascade_exact": sum(r["cascade"] == r["expected"] for r in cascade),
            "cascade_spurious": spurious_of(cascade, "cascade"),
            "qwen_exact": sum(r["qwen"] == r["expected"] for r in qwen_rows),
            "qwen_spurious": spurious_of(qwen_rows, "qwen"),
        },
        "rows": dev,
    }


def tone_report(out_of_fold, dev_rows, qwen):
    threshold = pick_tone_threshold(out_of_fold)
    dev = []
    for item, empathy, e_conf, confront, c_conf in dev_rows:
        decided = e_conf >= threshold and c_conf >= threshold
        fallback = qwen.get(item.utterance)
        final = (empathy, confront) if decided else fallback
        dev.append(
            {
                "utterance": item.utterance,
                "expected": [item.empathy, item.confrontational],
                "classifier": [empathy, confront] if decided else None,
                "qwen": list(fallback) if fallback else None,
                "cascade": list(final) if final else None,
                "confidence": [round(e_conf, 3), round(c_conf, 3)],
            }
        )

    def summary(key):
        rows = [r for r in dev if r[key] is not None]
        return {
            "lines": len(rows),
            "any_empathy_correct": sum((r[key][0] > 0) == (r["expected"][0] > 0) for r in rows),
            "empathy_false_positives": sum(r[key][0] > 0 and r["expected"][0] == 0 for r in rows),
            "level_correct": sum(r[key][0] == r["expected"][0] for r in rows),
            "confrontation_found": sum(r[key][1] and r["expected"][1] for r in rows),
            "confrontation_false_positives": sum(r[key][1] and not r["expected"][1] for r in rows),
        }

    by_threshold = [
        {"threshold": t, **tone_outcomes(out_of_fold, t)}
        for t in (0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95, 0.98)
    ]
    return {
        "threshold": threshold,
        "by_threshold": by_threshold,
        "training_out_of_fold": tone_outcomes(out_of_fold, threshold) | {"lines": len(out_of_fold)},
        "development": {
            "lines": len(dev),
            "confrontational_lines": sum(r["expected"][1] for r in dev),
            "classifier": summary("classifier"),
            "cascade": summary("cascade"),
            "qwen": summary("qwen"),
        },
        "rows": dev,
    }


async def evaluate(settings: Settings) -> dict:
    await verify_embedding_service(settings)
    embedder = Embedder(embedding_model(settings), classifier_cache(settings))
    cases = {case.id: case for case in load_cases(settings.cases_path)}
    try:
        training, development = topic_training(), topic_development()
        topics = topic_report(
            *await per_case_topics(embedder, cases, training, development), qwen_topics()
        )
        tone_items = tone_training()
        heads = await fit_tone(embedder, tone_items)
        tone = tone_report(
            await tone_out_of_fold(embedder, tone_items),
            await rate_tone(embedder, heads, tone_development()),
            qwen_tone(),
        )
    finally:
        embedder.save()
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "embedding_model": f"{settings.embedding_model_id}@{settings.embedding_model_revision}",
        "features": f"word 1-2 and character 3-5 n-gram TF-IDF + embedding x {EMBEDDING_WEIGHT}",
        "note": "Development data only; held-out test sets not read.",
        "topics": topics,
        "tone": tone,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = asyncio.run(evaluate(Settings(model_backend="local")))
    for name in ("topics", "tone"):
        part = report[name]
        keys = ("threshold", "training_out_of_fold", "development")
        print(name, json.dumps({k: part[k] for k in keys}, indent=1))
    if args.out:
        out = args.out if args.out.is_absolute() else ROOT / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
