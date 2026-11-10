"""Deterministic communication indicators for one candidate utterance.

These are descriptive rules, validated against author labels (`npm run eval:indicators`).
They are not CASC marking criteria and carry no clinical judgement.
"""

import re
from dataclasses import dataclass
from typing import Literal

INDICATORS_VERSION = "indicators-v1"

LEAD = (
    r"^(?:(?:and|so|ok|okay|right|well|now|um|mm-?hmm|i see|i understand|thanks|thank you)"
    r"[,.!]?\s+)*"
)
OPEN = re.compile(
    LEAD + r"(?:why\b|what\b(?!\s+(?:time|day|date|year|age|dose)\b)"
    r"|how\b(?!\s+(?:much|many|long|often|old|far)\b)"
    r"|in what way|tell me|describe|talk me through|go on|carry on|please go on"
    r"|(?:can|could|would) you (?:tell me|describe|say more|talk me|explain|walk me)|say more)",
    re.I,
)
CLOSED = re.compile(
    LEAD + r"(?:do|does|did|are|is|was|were|have|has|had|can|could|would|will|shall|should"
    r"|may|might|any|anything|anyone|how (?:much|many|long|often|old|far)|when|where|who"
    r"|whose|which|what (?:time|day|date|year|age|dose))\b",
    re.I,
)
SUMMARY = re.compile(
    r"\b(?:to summari[sz]e|in summary|to sum up|sum up|to recap|recap"
    r"|let me (?:just )?check i(?:'ve| have) got|if i(?:'ve| have) understood"
    r"|what i(?:'m| am) hearing|from what you(?:'ve| have) (?:said|told me)"
    r"|so,? you(?:'ve| have) (?:told|said))\b",
    re.I,
)
CHECK = re.compile(
    r"\b(?:does (?:that|this) (?:make sense|sound ok(?:ay)?)|any questions|what questions"
    r"|is (?:that|this|it|anything)(?: [a-z' ]+)? (?:clear|unclear|isn't clear)"
    r"|anything (?:i(?:'ve| have) said )?(?:that )?(?:isn't|is not) clear"
    r"|(?:explain|go over)(?: [a-z']+){0,2} again|in your own words"
    r"|what do you understand|what you understand)\b",
    re.I,
)
# Technical terms a patient or relative may not know; a prompt to explain, not an error.
JARGON = (
    "agranulocytosis",
    "anhedonia",
    "antipsychotic",
    "aetiology",
    "benzodiazepine",
    "cognitive",
    "comorbid",
    "delirium tremens",
    "delusion",
    "detoxification",
    "dysphoria",
    "euthymic",
    "full blood count",
    "hypomania",
    "ideation",
    "korsakoff",
    "myocarditis",
    "neutropenia",
    "neutrophil",
    "prognosis",
    "psychosis",
    "psychotic",
    "titrate",
    "titration",
    "treatment-resistant",
    "wernicke",
    "white cell count",
)
JARGON_RE = re.compile(r"\b(" + "|".join(re.escape(t) for t in JARGON) + r")\w*", re.I)


@dataclass(frozen=True)
class Tags:
    question: Literal["open", "closed", "none"]
    questions: int
    summary: bool
    check_understanding: bool
    jargon: tuple[str, ...]


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.?!])\s+", text.strip()) if s.strip()]


def question_type(sentence: str) -> Literal["open", "closed", "none"]:
    body = sentence.strip()
    if OPEN.search(body):
        return "open"
    if CLOSED.search(body) or body.endswith("?"):
        return "closed"
    return "none"


def tag(text: str) -> Tags:
    kinds = [question_type(s) for s in sentences(text)]
    asked = [k for k in kinds if k != "none"]
    kind = "open" if "open" in asked else "closed" if asked else "none"
    return Tags(
        question=kind,
        questions=len(asked),
        summary=bool(SUMMARY.search(text)),
        check_understanding=bool(CHECK.search(text)),
        jargon=tuple(dict.fromkeys(m.group(1).lower() for m in JARGON_RE.finditer(text))),
    )
