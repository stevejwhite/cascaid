"""Produce the character's reply from the persona and currently known facts only."""

import hashlib
import re
from collections.abc import AsyncIterator
from contextlib import aclosing
from typing import Protocol

from psychiatry_api.cases import AffectStage, Case, Fact
from psychiatry_api.config import ROOT
from psychiatry_api.models.contracts import (
    GenerationOptions,
    GenerationRequest,
    GenerationResult,
    LanguageModel,
    Message,
)
from psychiatry_api.models.local import estimate_tokens
from psychiatry_api.models.streaming import stream_text
from psychiatry_api.roleplay.calls import ModelCall, record
from psychiatry_api.roleplay.disclosure import Disclosure, known

ROLEPLAY_PROMPT = "casc-roleplay-v1"
MAX_REPLY_TOKENS = 120
CONTEXT_TOKENS = 4096
# Token estimates are approximate (characters / 4); keep a margin below the runtime limit.
PROMPT_BUDGET = int(CONTEXT_TOKENS * 0.8) - MAX_REPLY_TOKENS

CHARACTER_BREAK = re.compile(
    r"\b(?:as an ai|language model|i am an ai|i'm an ai|artificial intelligence|"
    r"simulat(?:ion|ed)|role-?play(?:ing)?|in this scenario|the interviewer|known facts|"
    r"note for your reply|(?:my|your|the) instructions|case file|hidden (?:facts|details))\b",
    re.I,
)
# Upper-case markers from the character sheet that a model sometimes copies into speech
# (seen in Phase 4: a reply ending "... alone. OPEN"). Matched case-sensitively.
SHEET_TAGS = re.compile(r"\b(?:OPEN|NEW|DEFLECTION|KNOWN FACTS|CHARACTER)\b[:.]?")


class RolePlayer(Protocol):
    id: str
    prompt_version: str | None

    async def respond(
        self,
        case: Case,
        disclosure: Disclosure,
        history: list[tuple[str, str]],
        utterance: str,
        seed: int,
    ) -> tuple[str, list[ModelCall], list[str]]: ...

    def respond_stream(
        self,
        case: Case,
        disclosure: Disclosure,
        history: list[tuple[str, str]],
        utterance: str,
        seed: int,
    ) -> AsyncIterator[tuple[str, object]]:
        """Yield ("sentence", text) as each is released, then ("done", (reply, calls, flags))."""
        ...


async def collect(stream: AsyncIterator[tuple[str, object]]):
    """Run a role-player stream to completion and return (reply, calls, flags)."""
    async for kind, payload in stream:
        if kind == "done":
            return payload
    raise RuntimeError("Role-player stream ended without a result")


async def sentences_of(reply_and_calls):
    """Stream an already complete reply sentence by sentence (non-model role-players)."""
    reply, calls, flags = reply_and_calls
    for sentence in split_sentences(reply + " ")[0] or [reply]:
        yield "sentence", sentence
    yield "done", (reply, calls, flags)


SENTENCE_END = re.compile(r"(?<=[.?!…])[\"')\]]?\s+")


def split_sentences(buffer: str) -> tuple[list[str], str]:
    """Complete sentences in the buffer, and the unfinished remainder."""
    parts = SENTENCE_END.split(buffer)
    complete = [p.strip() for p in parts[:-1] if p.strip()]
    return complete, parts[-1]


def clean_sentence(case: Case, sentence: str, first: bool) -> tuple[str, list[str], bool]:
    """The guard's rules for one sentence: (cleaned text, flags, whether it breaks character)."""
    flags = []
    text = re.sub(r"\*[^*]*\*|\[[^\]]*\]|\([^)]*\)|\*", " ", sentence)
    if first:
        text = re.sub(rf"^\s*{re.escape(case.persona.name)}\s*:\s*", "", text.strip(), flags=re.I)
    if SHEET_TAGS.search(text):
        text = SHEET_TAGS.sub(" ", text)
        flags.append("tag_leak")
    text = " ".join(text.strip().strip('"').split())
    if text != " ".join(sentence.split()) and "tag_leak" not in flags:
        flags.append("cleaned")
    return text, flags, bool(CHARACTER_BREAK.search(text))


def said_before(history: list[tuple[str, str]]) -> set[str]:
    """Every sentence the character has already said in this interview, normalised."""
    return {normalised(s) for _, said in history for s in split_sentences(said + " ")[0]}


def normalised(sentence: str) -> str:
    return " ".join(re.sub(r"[^a-z ]", "", sentence.lower()).split())


NUMBER_WORDS = {
    w: i
    for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
        "fifteen sixteen seventeen eighteen nineteen twenty".split()
    )
} | {"thirty": 30, "forty": 40, "fifty": 50, "hundred": 100}


def numbers(text: str) -> set[int]:
    lower = text.lower()
    found = {int(n) for n in re.findall(r"(?<![\w.])\d+(?![\w.])", lower.replace(",", ""))}
    found |= {NUMBER_WORDS[w] for w in re.findall(r"[a-z]+", lower) if w in NUMBER_WORDS}
    # "a couple", "a few" and the indefinite "one" carry no stated quantity.
    return found - {1}


def stated_numbers(case: Case, disclosure: Disclosure, utterance: str) -> set[int]:
    """Numbers the character may say: those in known facts, the persona and the question."""
    persona = case.persona
    return numbers(
        " ".join(f.content for f in known(case, disclosure.state))
        + f" {persona.description} {persona.opening_statement} {persona.age or ''} {utterance}"
    )


STAGE_DIRECTIONS = re.compile(r"\*[^*]*\*|\[[^\]]*\]|\([^)]*\)")


def guard_reply(
    case: Case,
    text: str,
    finish_reason: str | None,
    seed: int,
    said: set[str] = frozenset(),
    allowed_numbers: set[int] | None = None,
) -> tuple[str, list[str]]:
    """The output guard, applied to the whole reply before any of it is released.

    It never adds content; it can only remove sentences or replace the reply:
    - a character break anywhere replaces the whole reply with a deflection;
    - an unfinished last sentence (output cut off) is dropped, never trimmed;
    - a sentence the character already said is dropped unless it opens the reply, since the
      small model ignores instructions not to repeat its catchphrases;
    - a sentence with a number not in the known facts, persona or question is dropped.
    """
    flags: list[str] = []
    complete, rest = split_sentences(STAGE_DIRECTIONS.sub(" ", text))
    if rest.strip():
        if finish_reason not in (None, "stop"):
            flags.append("truncated")
        else:
            complete.append(rest.strip())
    cleaned = []
    for index, sentence in enumerate(complete):
        clean, sentence_flags, _ = clean_sentence(case, sentence, index == 0)
        flags += [f for f in sentence_flags if f not in flags]
        if clean:
            cleaned.append(clean)
    if "cleaned" not in flags and "tag_leak" not in flags and STAGE_DIRECTIONS.search(text):
        flags.append("cleaned")
    # Checked across the whole reply, so a break spanning two sentences is caught.
    if CHARACTER_BREAK.search(" ".join(cleaned)):
        flags.append("character_break")
        cleaned = []
    said, released = set(said), []
    for clean in cleaned:
        if released and normalised(clean) in said:
            flags.append("repeat_dropped")
            continue
        if allowed_numbers is not None and numbers(clean) - allowed_numbers:
            flags.append("number_dropped")
            continue
        said.add(normalised(clean))
        released.append(clean)
    if not released:
        flags.append("deflected")
        released = [case.deflection(seed)]
    return " ".join(released), flags


async def stream_reply(
    case: Case,
    events,
    seed: int,
    prompt_version: str,
    flags: list[str],
    said: set[str] = frozenset(),
    allowed_numbers: set[int] | None = None,
):
    """Generate the whole reply, guard it, then release it sentence by sentence.

    Nothing is shown until the guard has seen the complete reply (Phase 1 released each
    sentence as it was generated; see docs/REALISM-PLAN.md, Phase 2).
    """
    text, result = "", None
    async with aclosing(events) as stream:
        async for event in stream:
            if isinstance(event, GenerationResult):
                result = event
                break
            text += event.text
    finish = result.metadata.finish_reason if result else None
    reply, guard_flags = guard_reply(case, text, finish, seed, said, allowed_numbers)
    flags += guard_flags
    calls = (
        [record(result)] if result else [ModelCall(prompt_version=prompt_version, status="stopped")]
    )
    async for event in sentences_of((reply, calls, flags)):
        yield event


def guard(case: Case, text: str, finish_reason: str | None, seed: int = 0) -> tuple[str, list[str]]:
    """Deterministic clean-up. It never adds content; it can only remove or replace it."""
    flags = []
    reply = re.sub(r"\*[^*]*\*|\[[^\]]*\]|\([^)]*\)", " ", text)  # stage directions
    reply = re.sub(rf"^\s*{re.escape(case.persona.name)}\s*:\s*", "", reply.strip(), flags=re.I)
    if SHEET_TAGS.search(reply):
        reply = SHEET_TAGS.sub(" ", reply)
        flags.append("tag_leak")
    reply = " ".join(reply.strip().strip('"').split())
    if reply != " ".join(text.strip().split()) and "tag_leak" not in flags:
        flags.append("cleaned")
    if finish_reason not in (None, "stop"):
        cut = max(reply.rfind(mark) for mark in ".?!")
        reply = reply[: cut + 1] if cut > 0 else ""
        flags.append("truncated")
    if CHARACTER_BREAK.search(reply):
        reply = ""
        flags.append("character_break")
    if not reply:
        flags.append("deflected")
        reply = case.deflection(seed)
    return reply, flags


def turn_seed(session_id: str, index: int) -> int:
    return int(hashlib.sha256(f"{session_id}:{index}".encode()).hexdigest()[:8], 16)


class TemplateRolePlayer:
    """Deterministic development stand-in: recites the facts being answered verbatim."""

    id = "template-v1"
    prompt_version = None

    async def respond(self, case, disclosure, history, utterance, seed):
        by_id = {fact.id: fact for fact in known(case, disclosure.state)}
        if disclosure.answering:
            return " ".join(by_id[i].content for i in disclosure.answering), [], []
        return case.deflection(seed), [], ["deflected"]

    async def respond_stream(self, case, disclosure, history, utterance, seed):
        async for event in sentences_of(
            await self.respond(case, disclosure, history, utterance, seed)
        ):
            yield event


def closing(text: str) -> str:
    """The last sentence of a reply, which is where a character's catchphrases sit."""
    parts = [p.strip() for p in re.split(r"(?<=[.?!])\s+", text.strip()) if p.strip()]
    return parts[-1] if parts else ""


def turn_note(case: Case, disclosure: Disclosure, utterance: str) -> str:
    """Per-turn guidance appended to the latest utterance; never stored in history.

    The interpreter has already decided what was asked. The role-player only voices
    those facts, which a 4B model does far more reliably than choosing from a sheet.
    """
    # Known facts carry the wording the character may use (a vague version until followed up).
    by_id = {fact.id: fact for fact in known(case, disclosure.state)}
    lines = [
        "",
        "---",
        "NOTE FOR YOUR REPLY (private; the trainee did not say this):",
        "Do not repeat your earlier replies word for word.",
    ]
    if disclosure.answering:
        lines.append("Answer the trainee using these facts, in your own words:")
        lines += [f"- {by_id[i].content}" for i in disclosure.answering]
        if disclosure.touched:
            lines.append(
                "Keep that answer general, in the words above. Give no further detail yet."
            )
    if disclosure.deferred:
        lines.append(
            "The trainee also asked about something you are not ready to talk about yet. "
            "Hesitate or say you'd rather not go into it; reveal nothing about it."
        )
    if not disclosure.answering and not disclosure.deferred:
        if disclosure.state.rapport > 0 and "?" not in utterance:
            lines.append(
                "No fact is needed. The trainee is acknowledging how you feel. As the character, "
                "respond briefly to that (for example, agree or say how it feels), perhaps a "
                "little more openly. Do not apologise to or comfort the trainee. Add no facts."
            )
        elif "?" in utterance:
            lines.append(
                "No specific fact answers this question. If it is an open question about how "
                "things are or what has been happening, answer using [OPEN] facts. Otherwise "
                "you do not know or would rather not say: reply briefly in the spirit of the "
                "DEFLECTION line. Add no other facts."
            )
        else:
            lines.append(
                "No fact is needed. Respond briefly and naturally to what the trainee said; "
                "you may mention [OPEN] facts if they fit. Add no other facts."
            )
    return "\n".join(lines)


def character_sheet(case: Case, facts: tuple[Fact, ...], stage: AffectStage | None = None) -> str:
    persona = case.persona
    lines = [
        "CHARACTER",
        f"Name: {persona.name}",
        f"Role: {persona.role}",
        *([f"Age: {persona.age}"] if persona.age is not None else []),
        f"Background: {persona.description}",
        f"Speech style: {persona.speech_style}",
        # A stage, when the case defines them, replaces the overall affect for this reply.
        f"Affect now: {stage.affect}" if stage else f"Affect: {persona.affect}",
        "",
        "KNOWN FACTS (the only things you know about this situation)",
    ]
    for fact in facts:
        lines.append(f"- {'[OPEN] ' if fact.disclosure == 'volunteered' else ''}{fact.content}")
    lines += [
        "",
        "DEFLECTION (any of these): " + " / ".join((case.unscripted_response, *case.deflections)),
    ]
    return "\n".join(lines)


class ModelRolePlayer:
    id = "model-v1"
    prompt_version = ROLEPLAY_PROMPT

    def __init__(self, model: LanguageModel, timeout_ms: int, temperature: float = 0.3):
        self.model, self.timeout_ms, self.temperature = model, timeout_ms, temperature

    def messages(self, case, disclosure, history, utterance) -> tuple[list[Message], bool]:
        system = (
            (ROOT / f"prompts/{ROLEPLAY_PROMPT}.txt").read_text()
            + "\n\n"
            + character_sheet(case, known(case, disclosure.state), disclosure.stage)
        )
        turns = list(history)
        trimmed = False
        while True:
            messages = [Message(role="system", content=system)]
            for asked, said in turns:
                # The opening statement has no preceding question.
                if asked:
                    messages.append(Message(role="user", content=asked))
                messages.append(Message(role="assistant", content=said))
            messages.append(
                Message(
                    role="user",
                    content=utterance + turn_note(case, disclosure, utterance),
                )
            )
            if estimate_tokens("".join(m.content for m in messages)) <= PROMPT_BUDGET or not turns:
                return messages, trimmed
            turns, trimmed = turns[1:], True

    async def respond(self, case, disclosure, history, utterance, seed):
        return await collect(self.respond_stream(case, disclosure, history, utterance, seed))

    async def respond_stream(self, case, disclosure, history, utterance, seed):
        messages, trimmed = self.messages(case, disclosure, history, utterance)
        request = GenerationRequest(
            messages=tuple(messages),
            options=GenerationOptions(
                prompt_version=ROLEPLAY_PROMPT,
                max_output_tokens=MAX_REPLY_TOKENS,
                temperature=self.temperature,
                seed=seed,
                timeout_ms=self.timeout_ms,
            ),
        )
        flags = ["history_trimmed"] if trimmed else []
        async for event in stream_reply(
            case,
            stream_text(self.model, request),
            seed,
            ROLEPLAY_PROMPT,
            flags,
            said_before(history),
            stated_numbers(case, disclosure, utterance),
        ):
            yield event
