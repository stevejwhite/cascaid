"""Deterministic disclosure rules: which case facts the role-player may know, and when."""

from dataclasses import dataclass

from psychiatry_api.cases import AffectStage, Case, Fact

# Rapport is a running level: each turn it decays (x DECAY), then adds the utterance's
# empathy rating (0-2) and loses CONFRONTATION_COST for a confrontational line.
DECAY = 0.8
CONFRONTATION_COST = 1.0
MAX_RAPPORT = 3.0
# The level a rapport-gated fact needs. One brief empathic remark (1) reaches level 1 and
# keeps it for the next three turns; level 2 needs one specific remark or two brief ones
# close together.
REACHED = {1: 0.5, 2: 1.5}


@dataclass(frozen=True)
class Interpretation:
    """What one candidate utterance asked about, as decided by an interpreter."""

    asked: frozenset[str] = frozenset()
    # 0 none, 1 brief or generic, 2 specific (names the person's own feeling or situation).
    empathy: int = 0
    confrontational: bool = False
    # Whether the utterance responds to a question the character has just asked.
    answered: bool = False
    # The model interpreter's own paraphrase of the utterance, kept for error analysis.
    focus: str | None = None
    # Cascade interpreter only: which route decided topics and tone ("classifier" or
    # "model"), and the classifier's confidence in its best answer.
    topic_route: str | None = None
    topic_confidence: float | None = None
    # The topic classifier's best guess (a fact ID or "none") even when not confident.
    topic_leaning: str | None = None
    tone_route: str | None = None
    tone_confidence: float | None = None

    @property
    def rapport(self) -> bool:
        return self.empathy > 0


@dataclass(frozen=True)
class DisclosureState:
    # Facts revealed in full.
    unlocked: tuple[str, ...] = ()
    # The running rapport level (see DECAY).
    rapport: float = 0.0
    # Facts with a vague version that have been revealed only vaguely so far.
    touched: tuple[str, ...] = ()
    # Whether the previous candidate line was confrontational (affect stages last two turns).
    confronted: bool = False


@dataclass(frozen=True)
class Disclosure:
    state: DisclosureState
    # Gated facts revealed in full for the first time this turn.
    unlocked: tuple[str, ...] = ()
    # Facts the reply should use: asked about this turn and now known (new or earlier).
    answering: tuple[str, ...] = ()
    # Asked about but held back because rapport had not reached the fact's level. The
    # candidate must ask again once it has; a later empathic remark alone does not unlock it.
    deferred: tuple[str, ...] = ()
    # Facts revealed only in their vague version for the first time this turn.
    touched: tuple[str, ...] = ()
    # Interpreter output that names no fact in this case.
    ignored: tuple[str, ...] = ()
    # The character's affect stage for this reply, if the case defines stages.
    stage: AffectStage | None = None


def topics(case: Case) -> tuple[Fact, ...]:
    """Facts an interpreter listens for: every fact with question labels."""
    return tuple(fact for fact in case.facts if fact.asked_about)


def rapport_after(level: float, interpretation: Interpretation) -> float:
    level = level * DECAY + interpretation.empathy
    if interpretation.confrontational:
        level -= CONFRONTATION_COST
    return round(min(MAX_RAPPORT, max(0.0, level)), 3)


def needed(fact: Fact) -> float:
    return REACHED[fact.rapport_needed or 1]


def affect_stage(case: Case, level: float, confronted: bool) -> AffectStage | None:
    """The character's current affect: confrontation first, else the highest rapport stage
    reached, else the starting stage."""
    stages = case.affect_stages
    if not stages:
        return None
    if confronted:
        defensive = next((stage for stage in stages if stage.on_confrontation), None)
        if defensive:
            return defensive
    reached = [s for s in stages if s.rapport_at_least and level >= REACHED[s.rapport_at_least]]
    return max(reached, key=lambda s: s.rapport_at_least) if reached else stages[0]


def known(case: Case, state: DisclosureState) -> tuple[Fact, ...]:
    """Every fact the role-player may currently state, in case order.

    A fact revealed only vaguely is returned with its vague wording as its content, so
    every consumer (prompt, guard, evaluation) sees exactly what the character knows.
    """
    facts = []
    for fact in case.facts:
        if fact.disclosure == "volunteered" or fact.id in state.unlocked:
            facts.append(fact)
        elif fact.id in state.touched and fact.vague:
            facts.append(fact.model_copy(update={"content": fact.vague}))
    return tuple(facts)


def apply(case: Case, state: DisclosureState, interpretation: Interpretation) -> Disclosure:
    level = rapport_after(state.rapport, interpretation)
    facts = {fact.id: fact for fact in case.facts}
    unlocked, answering, deferred, touched = [], [], [], []
    for fact_id in interpretation.asked & facts.keys():
        fact = facts[fact_id]
        if fact.disclosure == "volunteered" or fact_id in state.unlocked:
            answering.append(fact_id)
        elif fact.disclosure == "after_rapport" and level < needed(fact):
            deferred.append(fact_id)
        elif fact.vague and fact_id not in state.touched:
            # First time asked: the vague version. Asking again gets the full detail.
            touched.append(fact_id)
            answering.append(fact_id)
        else:
            unlocked.append(fact_id)
            answering.append(fact_id)
    # Keep case order so prompts and logs are stable regardless of interpreter order.
    order = {fact_id: index for index, fact_id in enumerate(facts)}
    for ids in (unlocked, answering, deferred, touched):
        ids.sort(key=order.__getitem__)
    return Disclosure(
        state=DisclosureState(
            unlocked=state.unlocked + tuple(unlocked),
            rapport=level,
            touched=state.touched + tuple(touched),
            confronted=interpretation.confrontational,
        ),
        unlocked=tuple(unlocked),
        answering=tuple(answering),
        deferred=tuple(deferred),
        touched=tuple(touched),
        ignored=tuple(sorted(interpretation.asked - facts.keys())),
        stage=affect_stage(case, level, interpretation.confrontational or state.confronted),
    )
