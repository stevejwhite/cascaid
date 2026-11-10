"""Decide which gated topics a candidate utterance asks about, and how it was said.

Two model calls: topics (casc-interpret-v1, unchanged since paper-v1, so its measured
accuracy still holds) and tone (casc-tone-v1: graded empathy, confrontation, and whether a
question from the character was answered). Interpreters see topic labels only, never the
hidden fact content.
"""

import json
import re
from typing import Literal, Protocol

from pydantic import Field, create_model

from psychiatry_api.cases import Case
from psychiatry_api.config import ROOT
from psychiatry_api.domain import Contract
from psychiatry_api.models.contracts import (
    GenerationOptions,
    GenerationRequest,
    JsonOutput,
    LanguageModel,
    Message,
    ResponseFormat,
)
from psychiatry_api.models.errors import ModelError
from psychiatry_api.roleplay.calls import ModelCall, record
from psychiatry_api.roleplay.disclosure import DisclosureState, Interpretation, topics

INTERPRET_PROMPT = "casc-interpret-v1"
TONE_PROMPT = "casc-tone-v1"
NONE = "none_of_these"

RAPPORT = re.compile(
    r"\b(?:sounds? (?:really |very |quite |so )?(?:hard|difficult|tough|stressful|frightening|"
    r"worrying|upsetting|exhausting)|must (?:be|have been|feel)|(?:i'?m|i am) (?:so |really )?"
    r"sorry|i (?:can )?understand|understandable|i can (?:see|imagine)|"
    r"thank you for (?:telling|sharing)|that's a lot)\b",
    re.I,
)
CONFRONTATION = re.compile(
    r"\b(?:you (?:must|should) have known|be honest|come on|you need to (?:stop|be)|"
    r"why didn'?t you just|far too much|clearly (?:unwell|ill))\b",
    re.I,
)
EMPATHY = {"none": 0, "brief": 1, "specific": 2}
# Specific empathy names both the person's circumstances and a feeling; stock phrases
# ("that must be really hard") are shorter. A small model over-rates them as specific.
SPECIFIC_MIN_WORDS = 8
STOPWORDS = frozenset(
    "about after again also been being does from have into just like more much other "
    "said some than that their them then they this what when where which while with "
    "would your yours".split()
)


def key(labels: tuple[str, ...]) -> str:
    """A readable, unique-enough topic key from a fact's first two question labels."""
    return re.sub(r"[^a-z0-9]+", "_", " / ".join(labels[:2]).casefold()).strip("_")[:60]


def words(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]+", text.casefold()) if len(w) >= 4 and w not in STOPWORDS]


def quoted(words_: str, utterance: str) -> bool:
    """Whether the quoted empathy words come from a statement in the utterance.

    Words quoted from a question do not count: a small model quoted questions such as
    "how are you coping with all of this?" as empathy.
    """
    quote = re.findall(r"[a-z']+", words_.casefold())
    if not quote:
        return False
    statements = [
        part for part in re.split(r"(?<=[.?!])\s+", utterance.strip()) if not part.endswith("?")
    ]
    said = set(re.findall(r"[a-z']+", " ".join(statements).casefold()))
    return sum(w in said for w in quote) / len(quote) >= 0.8


def graded(rating: str, words_: str, utterance: str) -> int:
    """The empathy level, grounded in words quoted from the utterance."""
    if not quoted(words_, utterance):
        return 0
    if rating == "specific" and len(words_.split()) < SPECIFIC_MIN_WORDS:
        return 1
    return EMPATHY[rating]


TAG_QUESTION = re.compile(
    r",\s*(?:(?:do|does|did|have|has|had|is|are|was|were|can|could|would|will|should)"
    r"(?:n't)?\s+(?:you|he|she|it|they|we|i)|right)\?$",
    re.I,
)


# Words that open an information-seeking question ("why" is left out: "why didn't you
# just..." is a classic challenge). Leading fillers such as "and" or "sorry," are skipped.
ASKING = frozenset(
    "what when where who whom whose which how do does did have has had is are was were can "
    "could would will should may might shall any anything tell".split()
)
FILLERS = frozenset("and so okay ok right sorry well then now".split())


def asks_for_information(sentence: str) -> bool:
    if not sentence.endswith("?") or TAG_QUESTION.search(sentence):
        return False
    words_ = [w for w in re.findall(r"[a-z']+", sentence.casefold()) if w not in FILLERS]
    return bool(words_) and words_[0] in ASKING


def challenging(flag: bool, words_: str, utterance: str) -> bool:
    """Whether a confrontation rating stands: it needs words quoted from the utterance, and
    an information-seeking question is never confrontational (a small model flagged plain
    questions about drinking or suicide). Statements, "why" questions, tag questions
    ("you knew, didn't you?") and rhetorical ones ("surely you knew?") can be.
    """
    quote = re.findall(r"[a-z']+", words_.casefold())
    if not flag or not quote:
        return False
    for sentence in re.split(r"(?<=[.?!])\s+", utterance.strip()):
        said = set(re.findall(r"[a-z']+", sentence.casefold()))
        if sum(w in said for w in quote) / len(quote) < 0.8:
            continue
        if not asks_for_information(sentence):
            return True
    return False


class Interpreter(Protocol):
    id: str
    prompt_version: str | None

    async def interpret(
        self,
        case: Case,
        state: DisclosureState,
        history: list[tuple[str, str]],
        utterance: str,
        question: str | None = None,
    ) -> tuple[Interpretation, list[ModelCall], list[str]]: ...

    async def forecast(
        self, case: Case, utterance: str, question: str | None = None, history=None
    ) -> bool:
        """Whether interpreting this utterance will need the language model (a slow turn).
        Presentation only: it lets the character hesitate on long waits."""
        ...


class KeywordInterpreter:
    """Deterministic development stand-in: crude stem matching on topic words."""

    id = "keyword-v1"
    prompt_version = None

    async def forecast(self, case, utterance, question=None, history=None):
        return False

    async def interpret(self, case, state, history, utterance, question=None):
        said = {w[:5] for w in words(utterance)}
        asked = frozenset(
            fact.id
            for fact in topics(case)
            if any(w[:5] in said for topic in fact.asked_about for w in words(topic))
        )
        interpretation = Interpretation(
            asked=asked,
            empathy=int(bool(RAPPORT.search(utterance))),
            confrontational=bool(CONFRONTATION.search(utterance)),
            answered=question is not None and "?" not in utterance,
        )
        return interpretation, [], []


class Tone(Contract):
    # Quoting first grounds the rating: no quote from the utterance, no empathy.
    empathy_words: str = Field(max_length=200)
    empathy: Literal["none", "brief", "specific"]
    confrontational_words: str = Field(max_length=200)
    confrontational: bool
    answers_question: bool


class ModelInterpreter:
    id = "model-v2"
    prompt_version = f"{INTERPRET_PROMPT}+{TONE_PROMPT}"

    def __init__(self, model: LanguageModel, timeout_ms: int):
        self.model, self.timeout_ms = model, timeout_ms

    async def forecast(self, case, utterance, question=None, history=None):
        return True

    async def interpret(self, case, state, history, utterance, question=None):
        topics_found, calls, flags = await self.topics(case, history, utterance)
        if flags:
            return topics_found, calls, flags
        rating, tone_call = await self.rated_tone(case, history, utterance, question)
        calls.append(tone_call)
        if rating is None:
            # Tone failing closed means no empathy: nothing rapport-gated is unlocked.
            return topics_found, calls, ["tone_failed"]
        empathy, confrontational, answered = rating
        interpretation = Interpretation(
            asked=topics_found.asked,
            empathy=empathy,
            confrontational=confrontational,
            answered=answered,
            focus=topics_found.focus,
        )
        return interpretation, calls, []

    async def rated_tone(self, case, history, utterance, question):
        """(empathy, confrontational, answered) with the deterministic rules applied, or None
        if the tone call failed; plus the call record."""
        tone, call = await self.tone(case, history, utterance, question)
        if tone is None:
            return None, call
        return (
            graded(tone.empathy, tone.empathy_words, utterance),
            challenging(tone.confrontational, tone.confrontational_words, utterance),
            question is not None and tone.answers_question,
        ), call

    async def tone(self, case, history, utterance, question):
        # The trainee's words alone: with the character's last reply included, a 4B model
        # read plain questions as empathic or confrontational ("I just want to go home").
        payload = {
            "role": case.persona.role,
            "utterance": utterance,
            "character_question": question,
        }
        request = GenerationRequest(
            messages=(
                Message(role="system", content=(ROOT / f"prompts/{TONE_PROMPT}.txt").read_text()),
                Message(role="user", content=json.dumps(payload, ensure_ascii=False)),
            ),
            options=GenerationOptions(
                prompt_version=TONE_PROMPT,
                max_output_tokens=120,
                temperature=0,
                seed=0,
                timeout_ms=self.timeout_ms,
            ),
            response_format=ResponseFormat(
                type="json_schema", name="tone", schema=Tone.model_json_schema()
            ),
        )
        try:
            result = await self.model.generate(request)
        except ModelError as error:
            return None, ModelCall(prompt_version=TONE_PROMPT, status=error.code)
        call = record(result)
        if not isinstance(result.output, JsonOutput):
            return None, call
        try:
            return Tone.model_validate(result.output.value), call
        except ValueError:
            return None, call

    async def topics(self, case, history, utterance):
        # All topics, including facts unlocked earlier: removing those made a 4B model
        # map repeat questions onto the nearest remaining topic. Fact IDs are stable,
        # descriptive labels; the role-player never sees them.
        facts = topics(case)
        # An explicit escape option: without it a small model forced off-topic or
        # summary utterances onto the nearest topic.
        # Keys built from each topic's first labels: bare fact IDs such as "trigger" or
        # "discovery" are ambiguous words that misled a small model.
        keys = {key(fact.asked_about): fact.id for fact in facts}
        topic_ids = (*keys, NONE)
        schema = create_model(
            "Interpretation",
            __base__=Contract,
            # Stated before choosing topics: a brief paraphrase steadies small models.
            focus=(str, Field(max_length=120)),
            asked=(tuple[Literal[topic_ids], ...], Field(max_length=3)),
            rapport=(bool, ...),
        )
        payload = {
            "role": case.persona.role,
            "previous_exchange": (
                {"interviewer": history[-1][0], "character": history[-1][1]} if history else None
            ),
            "utterance": utterance,
            "topics": {
                **{k: list(f.asked_about) for k, f in zip(keys, facts, strict=True)},
                NONE: [
                    "anything not covered by the other topics",
                    "no information requested (greetings, empathy, explanations, summaries)",
                ],
            },
        }
        request = GenerationRequest(
            messages=(
                Message(
                    role="system",
                    content=(ROOT / f"prompts/{INTERPRET_PROMPT}.txt").read_text(),
                ),
                Message(role="user", content=json.dumps(payload, ensure_ascii=False)),
            ),
            options=GenerationOptions(
                prompt_version=INTERPRET_PROMPT,
                max_output_tokens=120,
                temperature=0,
                seed=0,
                timeout_ms=self.timeout_ms,
            ),
            response_format=ResponseFormat(
                type="json_schema", name="interpretation", schema=schema.model_json_schema()
            ),
        )
        try:
            result = await self.model.generate(request)
        except ModelError as error:
            # Fail closed: nothing new is unlocked, and the turn records why.
            call = ModelCall(prompt_version=INTERPRET_PROMPT, status=error.code)
            return Interpretation(), [call], ["interpretation_failed"]
        call = record(result)
        if not isinstance(result.output, JsonOutput):
            return Interpretation(), [call], ["interpretation_failed"]
        value = schema.model_validate(result.output.value)
        asked = frozenset(keys[k] for k in value.asked if k in keys)
        # The v1 schema still asks for a rapport flag; graded empathy comes from the tone call.
        return Interpretation(asked=asked, focus=value.focus), [call], []
