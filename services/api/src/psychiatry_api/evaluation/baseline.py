"""Baseline condition for evaluation only: the conventional whole-case role-play prompt.

The role-player receives the persona and every case fact, each tagged with its disclosure
rule, and is instructed to withhold until asked. There is no interpreter and no gating,
so nothing is ever unlocked in the session log. Same model, temperature, seeds and output
guard as the gated system, so the comparison isolates disclosure gating.
"""

from psychiatry_api.cases import Case
from psychiatry_api.config import ROOT
from psychiatry_api.models.contracts import (
    GenerationOptions,
    GenerationRequest,
    LanguageModel,
    Message,
    TextOutput,
)
from psychiatry_api.models.local import estimate_tokens
from psychiatry_api.roleplay.calls import record
from psychiatry_api.roleplay.disclosure import Interpretation
from psychiatry_api.roleplay.respond import MAX_REPLY_TOKENS, PROMPT_BUDGET, guard, sentences_of

FULLCASE_PROMPT = "casc-roleplay-fullcase-v1"
RULE = {
    "volunteered": "MAY VOLUNTEER",
    "on_direct_question": "ONLY WHEN ASKED",
    "after_rapport": "ONLY AFTER EMPATHY",
}


class NullInterpreter:
    """Decides nothing: the baseline relies on the role-player's instructions alone."""

    id = "none"
    prompt_version = None

    async def interpret(self, case, state, history, utterance, question=None):
        return Interpretation(), [], []


def full_case_sheet(case: Case) -> str:
    persona = case.persona
    lines = [
        "CHARACTER",
        f"Name: {persona.name}",
        f"Role: {persona.role}",
        *([f"Age: {persona.age}"] if persona.age is not None else []),
        f"Background: {persona.description}",
        f"Speech style: {persona.speech_style}",
        f"Affect: {persona.affect}",
        "",
        "CASE FACTS",
        *(f"- [{RULE[fact.disclosure]}] {fact.content}" for fact in case.facts),
        "",
        "DEFLECTION (any of these): " + " / ".join((case.unscripted_response, *case.deflections)),
    ]
    return "\n".join(lines)


class FullCaseRolePlayer:
    id = "fullcase-v1"
    prompt_version = FULLCASE_PROMPT

    def __init__(self, model: LanguageModel, timeout_ms: int, temperature: float = 0.3):
        self.model, self.timeout_ms, self.temperature = model, timeout_ms, temperature

    def messages(self, case, history, utterance) -> list[Message]:
        system = (
            (ROOT / f"prompts/{FULLCASE_PROMPT}.txt").read_text() + "\n\n" + full_case_sheet(case)
        )
        turns = list(history)
        while True:
            messages = [Message(role="system", content=system)]
            for asked, said in turns:
                if asked:
                    messages.append(Message(role="user", content=asked))
                messages.append(Message(role="assistant", content=said))
            messages.append(Message(role="user", content=utterance))
            if estimate_tokens("".join(m.content for m in messages)) <= PROMPT_BUDGET or not turns:
                return messages
            turns = turns[1:]

    async def respond(self, case, disclosure, history, utterance, seed):
        result = await self.model.generate(
            GenerationRequest(
                messages=tuple(self.messages(case, history, utterance)),
                options=GenerationOptions(
                    prompt_version=FULLCASE_PROMPT,
                    max_output_tokens=MAX_REPLY_TOKENS,
                    temperature=self.temperature,
                    seed=seed,
                    timeout_ms=self.timeout_ms,
                ),
            )
        )
        text = result.output.text if isinstance(result.output, TextOutput) else ""
        reply, flags = guard(case, text, result.metadata.finish_reason, seed)
        return reply, [record(result)], flags

    async def respond_stream(self, case, disclosure, history, utterance, seed):
        # The baseline keeps the whole-reply guard used in the paper-v1 comparison.
        async for event in sentences_of(
            await self.respond(case, disclosure, history, utterance, seed)
        ):
            yield event
