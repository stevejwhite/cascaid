from datetime import timedelta

import pytest

from psychiatry_api.cases import CASES_PATH, load_case
from psychiatry_api.feedback.indicators import tag
from psychiatry_api.feedback.report import report
from psychiatry_api.roleplay import sessions
from psychiatry_api.roleplay.interpret import KeywordInterpreter
from psychiatry_api.roleplay.respond import TemplateRolePlayer


@pytest.mark.parametrize(
    ("text", "question", "questions"),
    [
        ("How have you been feeling?", "open", 1),
        ("Tell me more about that.", "open", 1),
        ("So, how much do you drink?", "closed", 1),
        ("Do you smoke? How many a day?", "closed", 2),
        ("That sounds hard. What has helped?", "open", 1),
        ("I'm sorry to hear that.", "none", 0),
        ("What time did you take them?", "closed", 1),
    ],
)
def test_question_types(text, question, questions):
    tags = tag(text)
    assert (tags.question, tags.questions) == (question, questions)


def test_summary_check_and_jargon_tags():
    assert tag("So to summarise, things have been tough.").summary
    assert tag("Does that make sense?").check_understanding
    assert tag("We check for neutropenia and agranulocytosis.").jargon == (
        "neutropenia",
        "agranulocytosis",
    )
    assert tag("How are you?").jargon == ()


async def run(settings, tmp_path, case_id, lines, clock):
    case = load_case(CASES_PATH / f"{case_id}.yaml")
    store = sessions.SessionStore(tmp_path)
    interpreter, player = KeywordInterpreter(), TemplateRolePlayer()
    session = sessions.begin(store, sessions.create(store, settings, case, interpreter, player))
    for line in lines:
        clock.advance(30)
        session = await sessions.take_turn(store, session, line, interpreter, player)
    clock.advance(30)
    return sessions.end(store, session)


@pytest.fixture
def clock(monkeypatch):
    class Clock:
        now = sessions.now()

        def advance(self, seconds):
            self.now += timedelta(seconds=seconds)

    fake = Clock()
    monkeypatch.setattr(sessions, "now", lambda: fake.now)
    return fake


async def test_feedback_scores_only_asked_for_key_facts_and_times_them(settings, tmp_path, clock):
    session = await run(
        settings,
        tmp_path,
        "elevated-mood-history",
        [
            "Hi Alex, how have you been sleeping?",
            "Do you drink alcohol or use drugs?",
            "That must be frustrating. What do you think is happening, your understanding?",
            "So to summarise, you've slept very little this week.",
        ],
        clock,
    )
    feedback = report(session)
    facts = {f.id: f for f in feedback.information.facts}
    assert (facts["sleep-reduced"].status, facts["sleep-reduced"].question) == ("elicited", 1)
    assert facts["sleep-reduced"].seconds == 30
    assert facts["new-business"].status == "volunteered"
    assert facts["risk-driving"].status == "missed"
    key_gated = [f for f in session.case.facts if f.key and f.disclosure != "volunteered"]
    assert feedback.information.key_total == len(key_gated)
    assert feedback.information.key_elicited == sum(
        facts[f.id].status == "elicited" for f in key_gated
    )
    assert feedback.duration_seconds == 150 and feedback.ended_reason == "candidate_ended"
    tasks = {t.id: t for t in feedback.tasks}
    assert tasks["summarise"].status == "met" and "Question 4" in tasks["summarise"].evidence
    assert tasks["elicit-perspective"].status == "met"


async def test_communication_indicators_quote_their_source(settings, tmp_path, clock):
    session = await run(
        settings,
        tmp_path,
        "clozapine-explanation-relative",
        [
            "What do you know about clozapine?",
            "It can cause neutropenia, so we do blood tests. Does that make sense?",
            "Does he smoke? Does he use cannabis?",
        ],
        clock,
    )
    feedback = report(session)
    comm = feedback.communication
    assert (comm.open_questions, comm.closed_questions, comm.stacked) == (1, 2, 1)
    assert comm.open_share == pytest.approx(1 / 3)
    assert comm.checks_of_understanding == 1 and comm.jargon == ("neutropenia",)
    assert comm.empathy_source == "keyword"
    assert 0 < comm.candidate_word_share < 1
    tasks = {t.id: t for t in feedback.tasks}
    assert tasks["check-understanding"].status == "met"
    assert "Does that make sense?" in tasks["check-understanding"].evidence
    assert tasks["monitoring-explained"].status == "self_review"


async def test_unmet_tasks_and_unfinished_sessions(settings, tmp_path, clock):
    session = await run(
        settings, tmp_path, "memory-collateral-history", ["When did it start?"], clock
    )
    tasks = {t.id: t for t in report(session).tasks}
    assert tasks["acknowledge-carer"].status == "not_detected"
    assert tasks["acknowledge-carer"].evidence is None
    live = sessions.Session(session.events[:-1])
    with pytest.raises(ValueError, match="completed"):
        report(live)


def test_indicator_evaluation_reports_both_splits():
    from psychiatry_api.evaluation.indicators import evaluate

    result = evaluate()["by_split"]
    assert set(result) == {"development", "test"}
    assert result["test"]["items"] == 60
    assert result["development"]["all_correct"] == 1.0


async def test_phase_two_feedback_touched_journey_and_character_questions(
    settings, tmp_path, clock
):
    session = await run(
        settings,
        tmp_path,
        "memory-collateral-history",
        [
            "How is he managing the bills and cooking?",
            "Can you tell me more about the bills and cooking?",
            "Any worries about the cooker or gas?",
            "Not yet. I will come back to that once I know a bit more.",
            "That sounds really hard.",
            "Come on, you should have known something was wrong.",
            "Has anyone in the family had dementia?",
            "Does he drink or smoke?",
        ],
        clock,
    )
    turns = session.turns
    assert turns[0].touched == ("daily-function",) and turns[1].unlocked == ("daily-function",)
    assert "keeping on top of things" in turns[0].reply
    assert turns[2].question == "safe-alone" and turns[2].reply.endswith(
        "Is he safe living on his own?"
    )
    assert turns[3].answered is True and turns[2].answered is None
    feedback = report(session)
    facts = {f.id: f for f in feedback.information.facts}
    assert facts["daily-function"].status == "elicited"
    assert [(c.question, c.stage, c.cause) for c in feedback.journey] == [
        (0, "composed", "start"),
        (5, "tearful", "rapport"),
        (6, "hurt", "confrontation"),
        (8, "composed", "settled"),
    ]
    [question] = feedback.questions
    assert (question.id, question.asked_after, question.answered) == ("safe-alone", 3, True)
    assert question.response.startswith("Not yet")


async def test_a_fact_revealed_only_vaguely_is_touched_on(settings, tmp_path, clock):
    session = await run(
        settings, tmp_path, "memory-collateral-history", ["How is he with bills?"], clock
    )
    feedback = report(session)
    facts = {f.id: f for f in feedback.information.facts}
    assert facts["daily-function"].status == "touched_on" and facts["daily-function"].question == 1
    assert feedback.information.key_touched == 1 and feedback.information.key_elicited == 0


async def test_old_logs_replay_rapport_as_brief_empathy(settings, tmp_path, clock):
    session = await run(
        settings, tmp_path, "overdose-risk-assessment", ["That sounds really hard."], clock
    )
    path = tmp_path / f"{session.started.session_id}.jsonl"
    lines = path.read_text().splitlines()
    import json

    old = []
    for line in lines:
        event = json.loads(line)
        if event["type"] == "turn":
            for field in ("empathy", "rapport_level", "touched", "affect_stage", "question"):
                event.pop(field, None)
        old.append(json.dumps(event))
    path.write_text("\n".join(old) + "\n")
    replayed = sessions.SessionStore(tmp_path).load(session.started.session_id)
    assert replayed.state().rapport == 1.0
