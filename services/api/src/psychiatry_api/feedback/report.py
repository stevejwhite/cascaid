"""Post-station feedback computed deterministically from a session log.

Information gathering comes from the disclosure log; communication indicators from rules
on the candidate's words, plus the interpreter's rapport flag for empathy (model-assisted
and labelled as such). Nothing here is a CASC mark.
"""

from typing import Literal

from psychiatry_api.domain import Contract
from psychiatry_api.feedback.indicators import INDICATORS_VERSION, tag
from psychiatry_api.roleplay.sessions import Began, Ended, Interrupted, Session

NOTE = (
    "Automated feedback for practice. It shows which case information your questions "
    "elicited and describes how you asked; it is not a CASC mark, the case has not been "
    "clinically validated, and the indicators can be wrong."
)


class FactResult(Contract):
    id: str
    domain: str
    content: str
    key: bool
    # touched_on: only the vague version was revealed; a follow-up question was needed.
    status: Literal["elicited", "touched_on", "volunteered", "held_back", "missed"]
    question: int | None = None  # 1-based candidate question that elicited it
    seconds: int | None = None  # time into the interview


class DomainResult(Contract):
    domain: str
    elicited: int
    total: int


class Information(Contract):
    key_elicited: int
    key_touched: int = 0
    key_total: int
    facts: tuple[FactResult, ...]
    domains: tuple[DomainResult, ...]


class Utterance(Contract):
    question: int  # 1-based
    seconds: int
    text: str
    input: Literal["typed", "speech"]
    edited: bool | None
    question_type: Literal["open", "closed", "none"]
    questions: int
    summary: bool
    check_understanding: bool
    empathy: bool
    jargon: tuple[str, ...]


class Communication(Contract):
    utterances: int
    open_questions: int
    closed_questions: int
    open_share: float | None
    stacked: int
    empathy: int
    summaries: int
    checks_of_understanding: int
    jargon: tuple[str, ...]
    candidate_word_share: float | None
    spoken: int
    spoken_edited: int
    # Times the candidate spoke over the character (hands-free conversation).
    interruptions: int = 0
    rules_version: str = INDICATORS_VERSION
    empathy_source: Literal["model", "keyword"]


class AffectChange(Contract):
    """A change in the character's affect stage; question 0 is the start of the interview."""

    question: int
    stage: str
    affect: str
    cause: Literal["start", "rapport", "confrontation", "settled", "rapport_fell"]


class QuestionResult(Contract):
    id: str
    text: str
    asked_after: int  # the candidate question whose reply ended with this question
    answered: bool | None  # model-assisted; None if the station ended before a reply
    response: str | None


class TaskResult(Contract):
    id: str
    description: str
    status: Literal["met", "not_detected", "self_review"]
    evidence: str | None = None


class Feedback(Contract):
    note: str = NOTE
    ended_reason: Literal["candidate_ended", "time_up"]
    duration_seconds: int
    information: Information
    communication: Communication
    tasks: tuple[TaskResult, ...]
    utterances: tuple[Utterance, ...]
    journey: tuple[AffectChange, ...] = ()
    questions: tuple[QuestionResult, ...] = ()


def words(text: str) -> int:
    return len(text.split())


def report(session: Session) -> Feedback:
    case, began, ended = session.case, session.first(Began), session.first(Ended)
    if began is None or ended is None:
        raise ValueError("Feedback needs a completed interview")
    turns = session.turns
    seconds = [max(0, round((t.at - began.at).total_seconds())) for t in turns]

    first = {}
    for number, (turn, at) in enumerate(zip(turns, seconds, strict=True), 1):
        for fact_id in turn.unlocked:
            first.setdefault(fact_id, (number, at))
    touched = {}
    for number, (turn, at) in enumerate(zip(turns, seconds, strict=True), 1):
        for fact_id in turn.touched:
            touched.setdefault(fact_id, (number, at))
    held = {fact_id for turn in turns for fact_id in turn.deferred} - first.keys() - touched.keys()
    facts = []
    for fact in case.facts:
        if fact.disclosure == "volunteered":
            status, (number, at) = "volunteered", (None, None)
        elif fact.id in first:
            status, (number, at) = "elicited", first[fact.id]
        elif fact.id in touched:
            status, (number, at) = "touched_on", touched[fact.id]
        else:
            status, (number, at) = ("held_back" if fact.id in held else "missed"), (None, None)
        facts.append(
            FactResult(
                id=fact.id,
                domain=fact.domain,
                content=fact.content,
                key=fact.key,
                status=status,
                question=number,
                seconds=at,
            )
        )
    # Only facts the candidate had to ask for count towards the score.
    scored = [f for f in facts if f.key and f.status != "volunteered"]
    domains = {}
    for f in scored:
        elicited, total = domains.get(f.domain, (0, 0))
        domains[f.domain] = (elicited + (f.status == "elicited"), total + 1)

    utterances = []
    for number, (turn, at) in enumerate(zip(turns, seconds, strict=True), 1):
        tags = tag(turn.candidate)
        utterances.append(
            Utterance(
                question=number,
                seconds=at,
                text=turn.candidate,
                input=turn.input,
                edited=turn.edited,
                question_type=tags.question,
                questions=tags.questions,
                summary=tags.summary,
                check_understanding=tags.check_understanding,
                empathy=turn.rapport,
                jargon=tags.jargon,
            )
        )
    open_q = sum(u.question_type == "open" for u in utterances)
    closed_q = sum(u.question_type == "closed" for u in utterances)
    candidate_words = sum(words(t.candidate) for t in turns)
    character_words = words(began.opening) + sum(words(t.reply) for t in turns)
    talk = candidate_words + character_words
    communication = Communication(
        utterances=len(utterances),
        open_questions=open_q,
        closed_questions=closed_q,
        open_share=open_q / (open_q + closed_q) if open_q + closed_q else None,
        stacked=sum(u.questions > 1 for u in utterances),
        empathy=sum(u.empathy for u in utterances),
        summaries=sum(u.summary for u in utterances),
        checks_of_understanding=sum(u.check_understanding for u in utterances),
        jargon=tuple(dict.fromkeys(term for u in utterances for term in u.jargon)),
        candidate_word_share=candidate_words / talk if talk else None,
        spoken=sum(u.input == "speech" for u in utterances),
        spoken_edited=sum(bool(u.edited) for u in utterances),
        interruptions=sum(isinstance(e, Interrupted) for e in session.events),
        empathy_source="keyword" if session.started.interpreter.startswith("keyword") else "model",
    )

    by_fact = {f.id: f for f in facts}
    tasks = []
    for task in case.tasks:
        if task.evidence_fact:
            found = by_fact[task.evidence_fact]
            met = found.status in ("elicited", "volunteered")
            evidence = f"Question {found.question} elicited: “{found.content}”" if met else None
        elif task.evidence_indicator:
            field = {"open_question": "question_type"}.get(
                task.evidence_indicator, task.evidence_indicator
            )
            hit = next(
                (
                    u
                    for u in utterances
                    if (
                        getattr(u, field) == "open"
                        if field == "question_type"
                        else getattr(u, field)
                    )
                ),
                None,
            )
            met, evidence = (
                hit is not None,
                (f"Question {hit.question}: “{hit.text}”" if hit else None),
            )
        else:
            tasks.append(TaskResult(id=task.id, description=task.description, status="self_review"))
            continue
        tasks.append(
            TaskResult(
                id=task.id,
                description=task.description,
                status="met" if met else "not_detected",
                evidence=evidence,
            )
        )

    return Feedback(
        ended_reason=ended.reason,
        duration_seconds=max(0, round((ended.at - began.at).total_seconds())),
        information=Information(
            key_elicited=sum(f.status == "elicited" for f in scored),
            key_touched=sum(f.status == "touched_on" for f in scored),
            key_total=len(scored),
            facts=tuple(facts),
            domains=tuple(
                DomainResult(domain=d, elicited=e, total=t) for d, (e, t) in domains.items()
            ),
        ),
        communication=communication,
        tasks=tuple(tasks),
        utterances=tuple(utterances),
        journey=journey(session),
        questions=character_questions(session),
    )


def journey(session: Session) -> tuple[AffectChange, ...]:
    stages = {stage.id: stage for stage in session.case.affect_stages}
    if not stages:
        return ()
    first = session.case.affect_stages[0]
    changes = [AffectChange(question=0, stage=first.id, affect=first.affect, cause="start")]
    for number, turn in enumerate(session.turns, 1):
        if turn.affect_stage is None or turn.affect_stage == changes[-1].stage:
            continue
        stage = stages[turn.affect_stage]
        if stage.on_confrontation:
            cause = "confrontation"
        elif stages[changes[-1].stage].on_confrontation:
            cause = "settled"
        elif (stage.rapport_at_least or 0) > (stages[changes[-1].stage].rapport_at_least or 0):
            cause = "rapport"
        else:
            cause = "rapport_fell"
        changes.append(
            AffectChange(question=number, stage=stage.id, affect=stage.affect, cause=cause)
        )
    return tuple(changes)


def character_questions(session: Session) -> tuple[QuestionResult, ...]:
    texts = {q.id: q.text for q in session.case.questions}
    turns = session.turns
    results = []
    for number, turn in enumerate(turns, 1):
        if turn.question is None:
            continue
        reply = turns[number] if number < len(turns) else None
        results.append(
            QuestionResult(
                id=turn.question,
                text=texts.get(turn.question, turn.question),
                asked_after=number,
                answered=reply.answered if reply else None,
                response=reply.candidate if reply else None,
            )
        )
    return tuple(results)
