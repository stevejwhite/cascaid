"""The student interpreter's prompt and answer format, shared by training and runtime.

One call answers both questions the Qwen interpreter answers in two: which case topics the
trainee's line asks about (in the context of the previous exchange) and its tone. The
answer quotes the words behind any empathy or challenge, so the same deterministic rules
(quoted, graded, challenging) apply to it as to Qwen's tone call.
"""

import json
from dataclasses import dataclass

from psychiatry_api.cases import Case
from psychiatry_api.roleplay.disclosure import topics
from psychiatry_api.roleplay.interpret import NONE, challenging, graded, key

FORMAT_VERSION = "student-v3"

# The answer is short where it can be (generating it is most of the call's time), but
# topics are named by their descriptive keys: numbered topics cost a small model accuracy.
# t: topic keys; e: empathy level and ew the words quoted for it; c: confrontational and
# cw the words quoted for that.
SYSTEM = (
    "You label one line a doctor says in a psychiatric interview. Reply with JSON only: "
    '{"t": [keys of the topics the line asks the character about, at most 3, or ["'
    + NONE
    + '"]], "e": "none" | "brief" | "specific" (empathy), "ew": words copied from the line '
    'that show empathy, or "", "c": true | false (the line challenges, blames, lectures or '
    'dismisses), "cw": words copied from the line that do so, or ""}. Use the previous '
    "exchange only to understand what a short follow-up refers to."
)

EMPATHY_LEVELS = ("none", "brief", "specific")


def topic_keys(case: Case) -> dict[str, str]:
    """Topic key -> fact ID, the same keys the Qwen interpreter is shown."""
    return {key(fact.asked_about): fact.id for fact in topics(case)}


def render(case: Case, utterance: str, previous: tuple[str, str] | None = None) -> str:
    lines = [f"Role: {case.persona.role}", "Topics:"]
    for topic, fact in zip(topic_keys(case), topics(case), strict=True):
        lines.append(f"- {topic}: {'; '.join(fact.asked_about)}")
    lines.append(
        f"- {NONE}: no information asked (greetings, empathy, explanations, summaries), or "
        "anything not listed"
    )
    if previous:
        lines.append(
            f"Previous: doctor: {json.dumps(previous[0])} / character: {json.dumps(previous[1])}"
        )
    lines.append(f"Line: {json.dumps(utterance)}")
    return "\n".join(lines)


@dataclass(frozen=True)
class Label:
    asked: frozenset[str]  # fact IDs
    empathy: str  # none | brief | specific (before the deterministic rules)
    empathy_words: str
    confrontational: bool
    confrontational_words: str


def answer(case: Case, label: Label) -> str:
    """The training target for a label."""
    by_id = {fact_id: topic for topic, fact_id in topic_keys(case).items()}
    return json.dumps(
        {
            "t": sorted(by_id[f] for f in label.asked) or [NONE],
            "e": label.empathy,
            "ew": label.empathy_words,
            "c": label.confrontational,
            "cw": label.confrontational_words,
        },
        ensure_ascii=False,
    )


def parse(case: Case, text: str) -> Label | None:
    """A model's answer, or None if it is not valid (the caller then falls back)."""
    try:
        value = json.loads(text.strip().removeprefix("```json").removesuffix("```").strip())
        keys = topic_keys(case)
        asked = [t for t in value["t"] if t != NONE]
        if any(t not in keys for t in asked) or len(asked) > 3:
            return None
        if value["e"] not in EMPATHY_LEVELS:
            return None
        return Label(
            asked=frozenset(keys[t] for t in asked),
            empathy=value["e"],
            empathy_words=str(value.get("ew") or ""),
            confrontational=bool(value["c"]),
            confrontational_words=str(value.get("cw") or ""),
        )
    except (ValueError, KeyError, TypeError, AttributeError):
        return None


def tone(label: Label, utterance: str) -> tuple[int, bool]:
    """Empathy level and confrontation after the deterministic quote rules."""
    return (
        graded(label.empathy, label.empathy_words, utterance),
        challenging(label.confrontational, label.confrontational_words, utterance),
    )
