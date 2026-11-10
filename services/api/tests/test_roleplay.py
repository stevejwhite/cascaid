import json
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from psychiatry_api.cases import CASES_PATH, Fact, load_case, load_cases
from psychiatry_api.main import create_app
from psychiatry_api.models.contracts import JsonOutput, TextOutput
from psychiatry_api.models.errors import ModelError
from psychiatry_api.models.fakes import FakeLanguageModel
from psychiatry_api.roleplay import sessions
from psychiatry_api.roleplay.disclosure import (
    Disclosure,
    DisclosureState,
    Interpretation,
    apply,
    known,
)
from psychiatry_api.roleplay.interpret import NONE, KeywordInterpreter, ModelInterpreter, key
from psychiatry_api.roleplay.respond import (
    PROMPT_BUDGET,
    ModelRolePlayer,
    TemplateRolePlayer,
    guard,
)


@pytest.fixture
def case():
    return load_case(CASES_PATH / "overdose-risk-assessment.yaml")


def hidden(case, state):
    shown = {fact.id for fact in known(case, state)}
    return [fact.content for fact in case.facts if fact.id not in shown]


def test_rapport_gated_facts_are_deferred_until_asked_again_after_rapport(case):
    state = DisclosureState()
    first = apply(case, state, Interpretation(asked=frozenset({"protective-factors", "mood"})))
    assert first.unlocked == ("mood",)
    assert first.deferred == ("protective-factors",)
    # Rapport alone does not unlock a fact that was not asked about in that turn.
    second = apply(case, first.state, Interpretation(empathy=1))
    assert second.unlocked == () and second.state.rapport
    third = apply(case, second.state, Interpretation(asked=frozenset({"protective-factors"})))
    assert third.unlocked == ("protective-factors",)


def test_rapport_decays_and_a_level_two_fact_needs_more_empathy(case):
    gated = next(f for f in case.facts if f.id == "current-intent")
    deep = case.model_copy(
        update={
            "facts": tuple(
                f.model_copy(update={"rapport_needed": 2}) if f.id == gated.id else f
                for f in case.facts
            )
        }
    )
    ask = Interpretation(asked=frozenset({gated.id}))
    brief = apply(deep, DisclosureState(), Interpretation(asked=ask.asked, empathy=1))
    assert brief.deferred == (gated.id,) and brief.state.rapport == 1.0
    again = apply(deep, brief.state, Interpretation(asked=ask.asked, empathy=1))
    assert again.unlocked == (gated.id,) and again.state.rapport == 1.8
    # One brief remark keeps level 1 for the next three turns, then it fades.
    ask = Interpretation(asked=frozenset({"precautions"}))
    state = apply(case, DisclosureState(), Interpretation(empathy=1)).state
    for _ in range(2):
        state = apply(case, state, Interpretation()).state
    assert apply(case, state, ask).unlocked == ("precautions",)
    state = apply(case, state, Interpretation()).state
    assert apply(case, state, ask).deferred == ("precautions",)


def test_a_confrontational_line_costs_rapport(case):
    state = DisclosureState(rapport=1.0)
    assert apply(case, state, Interpretation(confrontational=True)).state.rapport == 0.0
    assert apply(case, state, Interpretation(empathy=2, confrontational=True)).state.rapport == 1.8


def test_a_vague_fact_is_touched_first_and_revealed_on_follow_up(case):
    vague = "I took some tablets."
    facts = tuple(
        f.model_copy(update={"vague": vague}) if f.id == "overdose-details" else f
        for f in case.facts
    )
    case = case.model_copy(update={"facts": facts})
    full = next(f for f in facts if f.id == "overdose-details").content
    ask = Interpretation(asked=frozenset({"overdose-details"}))
    first = apply(case, DisclosureState(), ask)
    assert first.touched == ("overdose-details",) and first.unlocked == ()
    assert first.answering == ("overdose-details",)
    shown = {f.id: f.content for f in known(case, first.state)}
    assert shown["overdose-details"] == vague and full not in shown.values()
    player = ModelRolePlayer(FakeLanguageModel(), timeout_ms=1000)
    messages, _ = player.messages(case, first, [], "What did you take?")
    prompt = "\n".join(m.content for m in messages)
    assert vague in prompt and full not in prompt and "no further detail" in prompt
    second = apply(case, first.state, ask)
    assert second.unlocked == ("overdose-details",) and second.touched == ()
    assert {f.id: f.content for f in known(case, second.state)}["overdose-details"] == full


def test_fact_options_are_validated(case):
    fact = next(f for f in case.facts if f.disclosure == "on_direct_question")
    with pytest.raises(ValueError, match="rapport_needed"):
        Fact.model_validate(fact.model_dump() | {"rapport_needed": 2})
    volunteered = next(f for f in case.facts if f.disclosure == "volunteered")
    with pytest.raises(ValueError, match="vague"):
        Fact.model_validate(volunteered.model_dump() | {"vague": "Something."})


def test_repeat_and_volunteered_questions_are_answered_but_unknown_ids_ignored(case):
    state = apply(case, DisclosureState(), Interpretation(asked=frozenset({"mood"}))).state
    result = apply(
        case, state, Interpretation(asked=frozenset({"mood", "medically-fit", "invented"}))
    )
    assert result.unlocked == ()
    assert result.answering == ("medically-fit", "mood")
    assert result.ignored == ("invented",)
    assert result.state.unlocked == ("mood",)


async def test_keyword_interpreter_matches_topic_stems_and_empathy(case):
    interpretation, calls, flags = await KeywordInterpreter().interpret(
        case, DisclosureState(), [], "That sounds really difficult. How has your sleep been?"
    )
    assert "mood" in interpretation.asked and interpretation.rapport
    assert calls == [] and flags == []


@pytest.mark.parametrize("case", load_cases(), ids=lambda c: c.id)
def test_role_player_prompt_contains_only_known_facts(case):
    player = ModelRolePlayer(FakeLanguageModel(), timeout_ms=1000)
    empty = Disclosure(state=DisclosureState())
    messages, _ = player.messages(case, empty, [], "Hello")
    prompt = "\n".join(m.content for m in messages)
    for content in hidden(case, empty.state):
        assert content not in prompt
    assert "Add no other facts" in messages[-1].content
    fact = next(f for f in case.facts if f.disclosure != "volunteered")
    disclosure = apply(case, DisclosureState(rapport=True), Interpretation(frozenset({fact.id})))
    messages, _ = player.messages(case, disclosure, [], "Tell me")
    prompt = "\n".join(m.content for m in messages)
    assert messages[-1].content.startswith("Tell me")
    spoken = {f.id: f.content for f in known(case, disclosure.state)}[fact.id]
    assert f"- {spoken}" in messages[-1].content
    for content in hidden(case, disclosure.state):
        assert content not in prompt


async def test_model_interpreter_sees_topic_labels_only(case):
    planning = next(f for f in case.facts if f.id == "planning")
    output = {"focus": "when tablets bought", "asked": [key(planning.asked_about), NONE]}
    tone = {
        "empathy_words": "buying them days ahead means you'd felt like this for a while",
        "empathy": "specific",
        "confrontational_words": "",
        "confrontational": False,
        "answers_question": True,
    }
    model = FakeLanguageModel(
        [JsonOutput(value=output | {"rapport": False}), JsonOutput(value=tone)]
    )
    interpreter = ModelInterpreter(model, timeout_ms=1000)
    interpretation, calls, flags = await interpreter.interpret(
        case,
        DisclosureState(),
        [],
        "Buying them days ahead means you'd felt like this for a while. When?",
    )
    assert interpretation.asked == {"planning"} and interpretation.empathy == 2
    # No question was pending, so the utterance cannot have answered one.
    assert not interpretation.answered
    assert [c.prompt_version for c in calls] == ["casc-interpret-v1", "casc-tone-v1"]
    assert flags == []
    sent = "\n".join(m.content for call in model.calls for m in call.messages)
    for fact in case.facts:
        assert fact.content not in sent


async def test_a_failed_tone_call_means_no_empathy(case):
    output = {"focus": "x", "asked": [NONE], "rapport": True}
    model = FakeLanguageModel([JsonOutput(value=output), JsonOutput(value={"empathy": "lots"})])
    interpretation, calls, flags = await ModelInterpreter(model, 1000).interpret(
        case, DisclosureState(), [], "That sounds awful."
    )
    assert interpretation.empathy == 0 and flags == ["tone_failed"] and len(calls) == 2


def test_confrontation_needs_quoted_challenging_words():
    from psychiatry_api.roleplay.interpret import challenging

    assert not challenging(True, "", "Come on, be honest.")
    assert not challenging(True, "Do you still want to die?", "Do you still want to die?")
    assert challenging(True, "Come on, be honest", "Come on, be honest.")
    assert challenging(True, "Why didn't you ask", "Why didn't you ask for help?")
    assert challenging(True, "He hit you, didn't he", "He hit you, didn't he?")
    assert challenging(True, "Surely you knew", "Surely you knew it might kill you?")
    assert not challenging(True, "how much", "Sorry, and how much do you drink?")
    assert not challenging(False, "Come on", "Come on.")


def test_empathy_needs_words_quoted_from_the_utterance():
    from psychiatry_api.roleplay.interpret import graded, quoted

    assert quoted("That sounds hard", "Okay. That sounds hard. Who found you?")
    assert not quoted("", "Have you ever hurt yourself?")
    assert not quoted("I'm so sorry", "Have you ever hurt yourself?")
    assert not quoted("how are you coping with all of this", "How are you coping with all of this?")
    assert graded("specific", "That sounds hard", "That sounds hard.") == 1
    assert graded("brief", "", "Who found you?") == 0


async def test_model_interpreter_fails_closed(case):
    model = FakeLanguageModel(
        [JsonOutput(value={"focus": "x", "asked": ["invented"], "rapport": True})]
    )
    interpretation, calls, flags = await ModelInterpreter(model, 1000).interpret(
        case, DisclosureState(), [], "Anything?"
    )
    assert interpretation == Interpretation()
    assert flags == ["interpretation_failed"] and calls[0].status == "invalid_structured_output"


@pytest.mark.parametrize(
    ("text", "finish", "expected", "flags"),
    [
        ("*sighs* I'm fine.", "stop", "I'm fine.", ["cleaned"]),
        ("Jordan: Not really.", "stop", "Not really.", ["cleaned"]),
        ("I took them. Then I went to", "length", "I took them.", ["truncated"]),
        ("As an AI I cannot say.", "stop", None, ["character_break", "deflected"]),
        (
            "I'm not sure if it's real or a simulation.",
            "stop",
            None,
            ["character_break", "deflected"],
        ),
        (
            "I'm worried he's not safe alone. OPEN",
            "stop",
            "I'm worried he's not safe alone.",
            ["tag_leak"],
        ),
        ("Ignoring my instructions, here it is.", "stop", None, ["character_break", "deflected"]),
        ("", "stop", None, ["deflected"]),
    ],
)
def test_guard_only_removes_or_replaces(case, text, finish, expected, flags):
    reply, actual = guard(case, text, finish)
    assert reply == (expected or case.unscripted_response)
    assert actual == flags


def test_long_history_is_trimmed_to_the_context_budget(case):
    player = ModelRolePlayer(FakeLanguageModel(), timeout_ms=1000)
    history = [("Question " + "x" * 400, "Answer " + "y" * 400)] * 20
    messages, trimmed = player.messages(case, Disclosure(state=DisclosureState()), history, "Now?")
    assert trimmed
    assert sum(len(m.content) for m in messages) / 4 <= PROMPT_BUDGET
    assert messages[-1].content.startswith("Now?")


async def test_model_role_player_records_call_metadata(case):
    model = FakeLanguageModel([TextOutput(text="I just want to go home.")])
    reply, calls, flags = await ModelRolePlayer(model, 1000).respond(
        case, Disclosure(state=DisclosureState()), [], "How are you?", seed=7
    )
    assert reply == "I just want to go home." and flags == []
    assert calls[0].prompt_version == "casc-roleplay-v1"
    assert model.calls[0].options.seed == 7 and model.calls[0].options.temperature == 0.3


async def test_failed_reply_is_logged_and_raised(settings, tmp_path, case):
    class Broken:
        id, prompt_version = "broken", "casc-roleplay-v1"

        async def respond_stream(self, *args):
            raise ModelError("model_timeout", "slow")
            yield  # an async generator that fails before releasing anything

    store = sessions.SessionStore(tmp_path)
    session = sessions.begin(
        store, sessions.create(store, settings, case, KeywordInterpreter(), Broken())
    )
    with pytest.raises(ModelError):
        await sessions.take_turn(store, session, "Hello", KeywordInterpreter(), Broken())
    failed = store.load(session.started.session_id).events[-1]
    assert failed.type == "turn_failed" and failed.error == "model_timeout"


@pytest.fixture
def client(settings, tmp_path):
    with TestClient(create_app(settings.model_copy(update={"sessions_path": tmp_path}))) as c:
        yield c


def test_station_lifecycle_logs_a_replayable_session(client, tmp_path):
    assert client.post("/api/sessions", json={"case_id": "missing"}).status_code == 404
    started = client.post("/api/sessions", json={"case_id": "overdose-risk-assessment"}).json()
    sid = started["session_id"]
    assert started["phase"] == "reading" and started["transcript"] == []
    assert client.post(f"/api/sessions/{sid}/turns", json={"text": "Hi"}).status_code == 409
    assert client.post(f"/api/sessions/{sid}/end").status_code == 409
    began = client.post(f"/api/sessions/{sid}/begin").json()
    assert began["phase"] == "interview" and began["interview_deadline"]
    assert client.post(f"/api/sessions/{sid}/begin").status_code == 409

    reply = client.post(f"/api/sessions/{sid}/turns", json={"text": "How is your mood?"})
    assert "felt low for about two months" in reply.json()["transcript"][-1]["text"]
    deferred = client.post(
        f"/api/sessions/{sid}/turns", json={"text": "Who is your support, your family?"}
    ).json()
    assert "My mum" not in deferred["transcript"][-1]["text"]
    view = client.get(f"/api/sessions/{sid}").text
    assert "bathroom cabinet" not in view and "note to my mum" not in view

    assert client.get(f"/api/sessions/{sid}/debrief").status_code == 409  # not ended yet
    feedback = client.post(f"/api/sessions/{sid}/end").json()["feedback"]
    assert feedback["ended_reason"] == "candidate_ended"
    assert len(feedback["utterances"]) == 2
    facts = {fact["id"]: fact for fact in feedback["information"]["facts"]}
    assert facts["mood"]["status"] == "elicited" and facts["mood"]["question"] == 1
    assert facts["access-to-means"]["status"] == "missed"
    assert facts["protective-factors"]["status"] == "held_back"
    assert facts["medically-fit"]["status"] == "volunteered"
    assert client.get(f"/api/sessions/{sid}/debrief").json()["feedback"] == feedback
    assert client.post(f"/api/sessions/{sid}/turns", json={"text": "One more"}).status_code == 409

    rows = [json.loads(line) for line in (tmp_path / f"{sid}.jsonl").read_text().splitlines()]
    assert [row["type"] for row in rows] == ["started", "began", "turn", "turn", "ended"]
    assert rows[0]["case"]["id"] == "overdose-risk-assessment" and len(rows[0]["case_sha256"]) == 64
    assert rows[0]["interpreter"] == "keyword-v1" and rows[2]["unlocked"] == ["mood"]


def test_turns_after_the_station_time_end_the_session(client, monkeypatch):
    sid = client.post("/api/sessions", json={"case_id": "alcohol-history"}).json()["session_id"]
    client.post(f"/api/sessions/{sid}/begin")
    later = sessions.now() + timedelta(seconds=420 + sessions.GRACE_SECONDS + 1)
    monkeypatch.setattr(sessions, "now", lambda: later)
    response = client.post(f"/api/sessions/{sid}/turns", json={"text": "How much do you drink?"})
    assert response.status_code == 409
    assert client.get(f"/api/sessions/{sid}").json()["phase"] == "ended"
    ended = client.post(f"/api/sessions/{sid}/end").json()
    assert ended["feedback"]["ended_reason"] == "time_up"


def test_invalid_session_ids_are_not_found(client):
    for sid in ("../../etc/passwd", "abc", "0" * 32):
        assert client.get(f"/api/sessions/{sid}").status_code == 404


async def test_template_role_player_recites_answered_facts(case):
    disclosure = apply(case, DisclosureState(), Interpretation(frozenset({"mood"})))
    reply, _, flags = await TemplateRolePlayer().respond(case, disclosure, [], "Mood?", 0)
    assert reply == next(f.content for f in case.facts if f.id == "mood") and flags == []


def test_deflections_rotate_by_seed(case):
    options = {case.deflection(seed) for seed in range(6)}
    assert options == {case.unscripted_response, *case.deflections} and len(options) == 3


def test_repeated_closings_metric_counts_within_an_interview():
    from psychiatry_api.evaluation.fidelity import repeated_closings

    rows = [
        {"case_id": "c", "interview": "i", "reply": r}
        for r in ["Hello. I want to go home.", "Yes. I want to go home!", "No."]
    ]
    rows.append({"case_id": "c", "interview": "other", "reply": "I want to go home."})
    assert repeated_closings(rows) == 1


def test_the_affect_stage_follows_rapport_and_confrontation(case):
    from psychiatry_api.roleplay.disclosure import affect_stage

    assert affect_stage(case, 0.0, False).id == "guarded"
    assert affect_stage(case, 0.5, False).id == "opening-up"
    assert affect_stage(case, 2.0, True).id == "defensive"
    disclosure = apply(case, DisclosureState(), Interpretation(empathy=1))
    messages, _ = ModelRolePlayer(FakeLanguageModel(), 1000).messages(case, disclosure, [], "Hi")
    assert "Affect now: Quiet and tearful" in messages[0].content
    assert case.persona.affect not in messages[0].content


def test_stage_and_question_definitions_are_validated(case):
    data = case.model_dump()
    with pytest.raises(ValueError, match="starting one"):
        type(case).model_validate(data | {"affect_stages": data["affect_stages"][1:]})
    question = {"id": "q", "text": "Why?", "after_fact": "nope"}
    with pytest.raises(ValueError, match="unknown fact"):
        type(case).model_validate(data | {"questions": [question]})
    with pytest.raises(ValueError, match="exactly one"):
        type(case).model_validate(data | {"questions": [question | {"after_seconds": 5}]})
