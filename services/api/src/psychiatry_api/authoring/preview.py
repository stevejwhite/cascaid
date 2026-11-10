"""Rule preview: the production disclosure rules run over author-chosen turns.

The author states what each line asked about and its tone, standing in for the
interpreter. The real `disclosure.apply` and `disclosure.known` decide the outcome; this
module only explains it. Question recognition and generated replies are not tested.
"""

from typing import Literal

from pydantic import Field

from psychiatry_api.cases import Case
from psychiatry_api.domain import Contract
from psychiatry_api.roleplay.disclosure import (
    REACHED,
    DisclosureState,
    Interpretation,
    apply,
    known,
    needed,
)

FactState = Literal["available", "held_back", "partial", "released"]
LABEL = "Rule preview: question recognition and generated replies are not tested."


class PreviewTurn(Contract):
    asked: tuple[str, ...] = Field(default=(), max_length=4)
    empathy: Literal[0, 1, 2] = 0
    confrontational: bool = False


class PreviewRequest(Contract):
    turns: tuple[PreviewTurn, ...] = Field(default=(), max_length=40)


class Outcome(Contract):
    fact_id: str
    result: Literal["available", "released", "partial", "held_back", "already_released"]
    reason: str


class FactView(Contract):
    fact_id: str
    state: FactState
    # The exact wording the role-player may now use: the vague version until followed up.
    permitted_text: str | None


class Step(Contract):
    turn: int
    rapport: float
    affect_stage: str | None
    affect: str | None
    outcomes: tuple[Outcome, ...]
    ignored: tuple[str, ...]
    character_question: str | None
    facts: tuple[FactView, ...]


class Group(Contract):
    title: str
    fact_ids: tuple[str, ...]


class Preview(Contract):
    label: str = LABEL
    groups: tuple[Group, ...]
    initial: tuple[FactView, ...]
    steps: tuple[Step, ...]
    note: str = (
        "Time-based character questions are not simulated. Rapport decays each turn, adds "
        "the line's empathy (0–2) and loses 1 for a confrontational line."
    )


def groups(case: Case) -> tuple[Group, ...]:
    def ids(condition) -> tuple[str, ...]:
        return tuple(f.id for f in case.facts if condition(f))

    result = [
        Group(
            title="Available from the start", fact_ids=ids(lambda f: f.disclosure == "volunteered")
        ),
        Group(
            title="Requires a question",
            fact_ids=ids(lambda f: f.disclosure == "on_direct_question"),
        ),
    ]
    for level in (1, 2):
        result.append(
            Group(
                title=f"Requires a question with rapport level {level}",
                fact_ids=ids(
                    lambda f, n=level: f.disclosure == "after_rapport" and needed(f) == REACHED[n]
                ),
            )
        )
    return tuple(group for group in result if group.fact_ids)


def views(case: Case, state: DisclosureState) -> tuple[FactView, ...]:
    permitted = {fact.id: fact.content for fact in known(case, state)}
    result = []
    for fact in case.facts:
        if fact.disclosure == "volunteered":
            status: FactState = "available"
        elif fact.id in state.unlocked:
            status = "released"
        elif fact.id in state.touched:
            status = "partial"
        else:
            status = "held_back"
        result.append(
            FactView(fact_id=fact.id, state=status, permitted_text=permitted.get(fact.id))
        )
    return tuple(result)


def explain(case: Case, before: DisclosureState, disclosure, level: float) -> list[Outcome]:
    facts = {fact.id: fact for fact in case.facts}
    outcomes = []
    for fact_id in disclosure.answering + disclosure.deferred:
        fact = facts[fact_id]
        if fact_id in disclosure.deferred:
            needs = fact.rapport_needed or 1
            outcomes.append(
                Outcome(
                    fact_id=fact_id,
                    result="held_back",
                    reason=f"Needs rapport level {needs} (at least {REACHED[needs]}); rapport "
                    f"was {level:.2f} after this line. Asking again once rapport is reached "
                    "releases it; a later empathic remark alone does not.",
                )
            )
        elif fact.disclosure == "volunteered":
            outcomes.append(
                Outcome(
                    fact_id=fact_id,
                    result="available",
                    reason="Volunteered fact: always available to the character.",
                )
            )
        elif fact_id in disclosure.touched:
            outcomes.append(
                Outcome(
                    fact_id=fact_id,
                    result="partial",
                    reason="First question about this fact: the vague answer is given. Asking "
                    "again releases the full answer.",
                )
            )
        elif fact_id in disclosure.unlocked:
            if fact_id in before.touched:
                reason = "Asked again after the vague answer: released in full."
            elif fact.disclosure == "after_rapport":
                needs = fact.rapport_needed or 1
                reason = (
                    f"Asked with rapport {level:.2f}, at least the {REACHED[needs]} "
                    f"needed for level {needs}: released."
                )
            else:
                reason = "Asked directly: released."
            outcomes.append(Outcome(fact_id=fact_id, result="released", reason=reason))
        else:
            outcomes.append(
                Outcome(
                    fact_id=fact_id,
                    result="already_released",
                    reason="Already released earlier in the interview.",
                )
            )
    return outcomes


def preview(case: Case, request: PreviewRequest) -> Preview:
    state = DisclosureState()
    asked_questions: set[str] = set()
    steps = []
    for number, turn in enumerate(request.turns, start=1):
        before = state
        disclosure = apply(
            case,
            state,
            Interpretation(
                asked=frozenset(turn.asked),
                empathy=turn.empathy,
                confrontational=turn.confrontational,
            ),
        )
        state = disclosure.state
        # Mirrors the session's due question: the first unasked one whose fact is revealed.
        revealed = set(state.unlocked) | set(state.touched)
        question = next(
            (
                q
                for q in case.questions
                if q.id not in asked_questions and q.after_fact and q.after_fact in revealed
            ),
            None,
        )
        if question:
            asked_questions.add(question.id)
        steps.append(
            Step(
                turn=number,
                rapport=state.rapport,
                affect_stage=disclosure.stage.id if disclosure.stage else None,
                affect=disclosure.stage.affect if disclosure.stage else None,
                outcomes=tuple(explain(case, before, disclosure, state.rapport)),
                ignored=disclosure.ignored,
                character_question=question.text if question else None,
                facts=views(case, state),
            )
        )
    return Preview(groups=groups(case), initial=views(case, DisclosureState()), steps=tuple(steps))
