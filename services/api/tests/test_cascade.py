from dataclasses import replace
from pathlib import Path

import pytest

from psychiatry_api.cases import CASES_PATH, load_case, load_cases
from psychiatry_api.models.contracts import JsonOutput
from psychiatry_api.models.errors import ModelError
from psychiatry_api.models.fakes import FakeEmbeddingModel, FakeLanguageModel
from psychiatry_api.roleplay.classify import (
    TRAINING,
    CascadeInterpreter,
    Rating,
    TrainedClassifiers,
    topic_training,
)
from psychiatry_api.roleplay.disclosure import DisclosureState
from psychiatry_api.roleplay.interpret import NONE, ModelInterpreter, key


@pytest.fixture
def case():
    return load_case(CASES_PATH / "overdose-risk-assessment.yaml")


class Stub:
    """Stands in for trained classifiers with a fixed rating."""

    version = "classifier-v1-test"

    def __init__(self, rating: Rating | None = None, error: bool = False):
        self.rating, self.error = rating, error

    async def ready(self, cases):
        if self.error:
            raise ModelError("model_unavailable", "embedding server down")

    async def rate(self, case, utterance):
        return self.rating


CONFIDENT = Rating(frozenset({"note"}), 0.97, 1, 0.95, False, 0.99)


def qwen(case, *outputs):
    model = FakeLanguageModel([JsonOutput(value=v) for v in outputs])
    return model, ModelInterpreter(model, 1000)


TOPIC = {"focus": "x", "asked": [NONE], "rapport": False}
TONE = {
    "empathy_words": "",
    "empathy": "none",
    "confrontational_words": "",
    "confrontational": False,
    "answers_question": True,
}


async def test_confident_classifiers_need_no_model_call(case):
    model, interpreter = qwen(case)
    cascade = CascadeInterpreter(Stub(CONFIDENT), interpreter, {case.id: case})
    result, calls, flags = await cascade.interpret(
        case, DisclosureState(), [], "Did you leave a note? That sounds hard."
    )
    assert result.asked == {"note"} and result.empathy == 1 and not result.confrontational
    assert (result.topic_route, result.tone_route) == ("classifier", "classifier")
    assert calls == [] and flags == [] and model.calls == []


async def test_unconfident_answers_go_to_the_model(case):
    model, interpreter = qwen(case, TOPIC | {"asked": [key(case.facts[1].asked_about)]}, TONE)
    unsure = Rating(None, 0.6, 2, 0.55, False, 0.99)
    cascade = CascadeInterpreter(Stub(unsure), interpreter, {case.id: case})
    result, calls, _ = await cascade.interpret(case, DisclosureState(), [], "What happened?")
    assert result.asked == {case.facts[1].id} and result.empathy == 0
    assert (result.topic_route, result.tone_route) == ("model", "model")
    assert [c.prompt_version for c in calls] == ["casc-interpret-v1", "casc-tone-v1"]
    assert result.topic_confidence == 0.6 and result.tone_confidence == 0.55


async def test_a_pending_character_question_is_always_judged_by_the_model(case):
    model, interpreter = qwen(case, TONE)
    cascade = CascadeInterpreter(Stub(CONFIDENT), interpreter, {case.id: case})
    result, calls, _ = await cascade.interpret(
        case, DisclosureState(), [], "You can go home soon.", "Can I go home?"
    )
    assert result.topic_route == "classifier" and result.tone_route == "model"
    assert result.answered and len(calls) == 1


async def test_without_the_embedding_server_it_behaves_like_the_model_interpreter(case):
    model, interpreter = qwen(case, TOPIC, TONE)
    cascade = CascadeInterpreter(Stub(error=True), interpreter, {case.id: case})
    result, calls, flags = await cascade.interpret(case, DisclosureState(), [], "Hello.")
    assert flags == ["classifier_unavailable"] and len(calls) == 2
    assert result.topic_route is None


async def test_trained_classifiers_cover_every_case_with_training_data(tmp_path):
    cases = {case.id: case for case in load_cases()}
    classifiers = TrainedClassifiers(FakeEmbeddingModel(dimensions=8), tmp_path / "cache.npz")
    await classifiers.ready(cases)
    # A topic classifier for every case with training lines; a new case without any is
    # left to the student and Qwen until its lines are written.
    trained = {item.case_id for item in topic_training()}
    assert set(classifiers.topic) == trained & set(cases)
    untrained = next((c for c in cases.values() if c.id not in trained), None)
    if untrained is not None:
        assert (await classifiers.rate(untrained, "How are you feeling?")).topics is None
    assert classifiers.version.startswith("classifier-v1-")
    assert (tmp_path / "cache.npz").exists()
    rating = await classifiers.rate(
        cases["overdose-risk-assessment"], "Do you drink? Do you smoke?"
    )
    # Two questions in one line always defer to the model.
    assert rating.topics is None
    question_only = await classifiers.rate(cases["overdose-risk-assessment"], "Who found you?")
    assert question_only.empathy == 0 and question_only.empathy_confidence == 1.0
    assert replace(question_only, topics=None).confrontation_confidence == 1.0


class Counting(Stub):
    def __init__(self, rating):
        super().__init__(rating)
        self.rated = 0

    async def rate(self, case, utterance):
        self.rated += 1
        return self.rating


async def test_forecast_says_whether_the_turn_will_wait_for_the_model(case):
    _, interpreter = qwen(case)
    unsure = Rating(None, 0.6, 2, 0.55, False, 0.99)
    fast = CascadeInterpreter(Stub(CONFIDENT), interpreter, {case.id: case})
    assert await fast.forecast(case, "Did you leave a note?") is False
    assert await fast.forecast(case, "Can you go home?", "Can I go home?") is True
    assert (
        await CascadeInterpreter(Stub(unsure), interpreter, {case.id: case}).forecast(case, "x")
        is True
    )
    assert (
        await CascadeInterpreter(Stub(error=True), interpreter, {case.id: case}).forecast(case, "x")
        is True
    )
    assert await interpreter.forecast(case, "x") is True


async def test_the_forecast_rating_is_reused_by_the_interpretation(case):
    model, interpreter = qwen(case)
    classifiers = Counting(CONFIDENT)
    cascade = CascadeInterpreter(classifiers, interpreter, {case.id: case})
    await cascade.forecast(case, "Did you leave a note?")
    await cascade.interpret(case, DisclosureState(), [], "Did you leave a note?")
    assert classifiers.rated == 1
    await cascade.interpret(case, DisclosureState(), [], "Did you leave a note?")
    assert classifiers.rated == 2  # used once, not kept for later turns


class FakeStudentModel:
    """Answers like the served student; records what it was sent."""

    def __init__(self, text: str | None):
        self.text, self.sent = text, []

    async def complete(self, system, user):
        from psychiatry_api.models.student import StudentReply

        self.sent.append(user)
        if self.text is None:
            raise ModelError("model_unavailable", "down")
        return StudentReply(self.text, 300, 500, 20, 480)


def student(text, cross_check="off"):
    from psychiatry_api.finetune.format import FORMAT_VERSION
    from psychiatry_api.roleplay.classify import StudentTopics

    served = {"model": "student-test", "format_version": FORMAT_VERSION, "weights_sha256": "a" * 64}
    model = FakeStudentModel(text)
    return StudentTopics(model, served, cross_check), model


UNSURE = Rating(None, 0.6, 0, 0.95, False, 0.99)


async def test_the_student_decides_topics_the_classifiers_are_unsure_of(case):
    from psychiatry_api.finetune.format import Label, answer

    model, interpreter = qwen(case)  # no Qwen output queued: a Qwen call would fail
    reply = answer(case, Label(frozenset({"note"}), "none", "", False, ""))
    topics, served = student(reply)
    cascade = CascadeInterpreter(Stub(UNSURE), interpreter, {case.id: case}, topics)
    history = [("", "Opening."), ("Did anyone find you?", "My flatmate did.")]
    result, calls, flags = await cascade.interpret(case, DisclosureState(), history, "And a note?")
    assert result.asked == {"note"} and result.topic_route == "student"
    assert result.tone_route == "classifier" and model.calls == [] and flags == []
    assert calls[0].prompt_version.startswith("student-") and calls[0].model_id == "student-test"
    assert 'Previous: doctor: "Did anyone find you?"' in served.sent[0]
    assert cascade.id == "cascade-v2" and "student-test" in cascade.prompt_version
    assert await cascade.forecast(case, "And a note?") is False  # no Qwen call needed


async def test_a_failed_or_invalid_student_answer_falls_back_to_qwen(case):
    for text in (None, "not json"):
        model, interpreter = qwen(case, TOPIC | {"asked": [key(case.facts[1].asked_about)]})
        topics, _ = student(text)
        cascade = CascadeInterpreter(Stub(UNSURE), interpreter, {case.id: case}, topics)
        result, calls, flags = await cascade.interpret(
            case, DisclosureState(), [], "What happened?"
        )
        assert result.topic_route == "model" and result.asked == {case.facts[1].id}
        assert flags in (["student_failed"], ["student_unsure"])
        assert calls[0].status != "completed"


def test_a_student_trained_on_another_format_is_refused():
    from psychiatry_api.roleplay.classify import StudentTopics

    with pytest.raises(ValueError):
        StudentTopics(
            FakeStudentModel("{}"),
            {"model": "m", "format_version": "student-v0", "weights_sha256": "b" * 64},
        )


async def test_the_student_adapter_posts_to_loopback_with_thinking_off():
    import json

    import httpx

    from psychiatry_api.models.student import StudentModel

    seen = {}

    def handler(request):
        seen["url"], seen["body"] = str(request.url), json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "{}"}}],
                "usage": {"prompt_tokens": 500, "completion_tokens": 9},
            },
        )

    model = StudentModel("http://127.0.0.1:8184", "s", 5, httpx.MockTransport(handler))
    reply = await model.complete("SYSTEM", "USER")
    assert seen["url"] == "http://127.0.0.1:8184/v1/chat/completions"
    assert seen["body"]["chat_template_kwargs"] == {"enable_thinking": False}
    assert seen["body"]["temperature"] == 0 and reply.text == "{}" and reply.input_tokens == 500
    with pytest.raises(ModelError):
        StudentModel("https://student.example.com", "s", 5)


async def test_a_student_none_for_an_information_question_is_checked_by_qwen(case):
    from psychiatry_api.finetune.format import Label, answer

    none = answer(case, Label(frozenset(), "none", "", False, ""))
    model, interpreter = qwen(case, TOPIC | {"asked": [key(case.facts[1].asked_about)]})
    topics, _ = student(none)
    cascade = CascadeInterpreter(Stub(UNSURE), interpreter, {case.id: case}, topics)
    result, calls, _ = await cascade.interpret(
        case, DisclosureState(), [], "Did you take anything?"
    )
    assert result.topic_route == "model" and calls[0].status == "unsure"
    # A statement with no question stays with the student's "none".
    model, interpreter = qwen(case)
    topics, _ = student(none)
    cascade = CascadeInterpreter(Stub(UNSURE), interpreter, {case.id: case}, topics)
    result, _, _ = await cascade.interpret(case, DisclosureState(), [], "That sounds really hard.")
    assert result.topic_route == "student" and result.asked == frozenset()


async def test_forecast_asks_the_student_once_and_reports_its_hand_off(case):
    from psychiatry_api.finetune.format import Label, answer

    none = answer(case, Label(frozenset(), "none", "", False, ""))
    model, interpreter = qwen(case, TOPIC)
    topics, served = student(none)
    cascade = CascadeInterpreter(Stub(UNSURE), interpreter, {case.id: case}, topics)
    assert await cascade.forecast(case, "Did you take anything?", history=[]) is True
    await cascade.interpret(case, DisclosureState(), [], "Did you take anything?")
    assert len(served.sent) == 1  # the forecast's answer was reused


async def test_two_questions_in_one_line_skip_the_student(case):
    model, interpreter = qwen(case, TOPIC)
    topics, served = student("{}")
    cascade = CascadeInterpreter(Stub(UNSURE), interpreter, {case.id: case}, topics)
    line = "Do you drink much, and is there anything else at home you could take?"
    assert await cascade.forecast(case, line, history=[]) is True
    result, _, _ = await cascade.interpret(case, DisclosureState(), [], line)
    assert result.topic_route == "model" and served.sent == []


def test_joined_questions_count_as_two():
    from psychiatry_api.roleplay.classify import compound

    for line in (
        "Do you smoke, and how is your appetite?",
        "Does he drink? Does he smoke?",
        "Do you drink, and have you been ill like this before?",
    ):
        assert compound(line), line
    for line in (
        "How is he coping with everyday tasks?",
        "Fish and chips, was it?",
        "That sounds hard, and I'm sorry.",
    ):
        assert not compound(line), line


async def test_a_student_topic_for_a_statement_or_leading_question_goes_to_qwen(case):
    from psychiatry_api.finetune.format import Label, answer

    note = answer(case, Label(frozenset({"note"}), "none", "", False, ""))
    for line in ("I'm sorry, that sounds hard.", "You left a note, didn't you?"):
        model, interpreter = qwen(case, TOPIC)
        topics, _ = student(note)
        cascade = CascadeInterpreter(Stub(UNSURE), interpreter, {case.id: case}, topics)
        result, calls, _ = await cascade.interpret(case, DisclosureState(), [], line)
        assert result.topic_route == "model" and calls[0].status == "unsure", line


def test_what_counts_as_asking():
    from psychiatry_api.roleplay.classify import asks_question

    for line in ("And a note?", "Did you leave a note?", "Okay. How much do you drink?"):
        assert asks_question(line), line
    for line in (
        "Daniel has been aggressive at home, hasn't he?",
        "I'm sorry, that sounds hard.",
        "Surely you knew it might kill you?",
        "Come on, you must have known.",
    ):
        assert not asks_question(line), line


async def test_a_student_none_stands_when_the_classifiers_lean_to_no_topic(case):
    from dataclasses import replace

    from psychiatry_api.finetune.format import Label, answer

    none = answer(case, Label(frozenset(), "none", "", False, ""))
    model, interpreter = qwen(case)  # a Qwen call would fail
    topics, _ = student(none)
    leaning = replace(UNSURE, leaning="none")
    cascade = CascadeInterpreter(Stub(leaning), interpreter, {case.id: case}, topics)
    line = "What's been going on for you?"
    assert await cascade.forecast(case, line, history=[]) is False
    result, _, _ = await cascade.interpret(case, DisclosureState(), [], line)
    assert result.topic_route == "student" and result.asked == frozenset()


@pytest.mark.parametrize(
    ("asked", "leaning", "mode", "to_qwen"),
    [
        ({"a"}, "b", "off", False),
        ({"a"}, "a", "fact", False),  # the two judges agree
        ({"a"}, "b", "fact", True),  # a neighbouring fact: Qwen decides
        ({"a"}, "none", "fact", False),
        ({"a"}, "none", "all", True),
        ({"a", "b"}, "b", "all", False),
        ({"a"}, None, "all", False),  # no classifier for this case: nothing to compare
        (set(), "b", "all", False),  # "none" answers are handled by the existing rule
    ],
)
def test_cross_check_decision_table(asked, leaning, mode, to_qwen):
    from psychiatry_api.roleplay.classify import disagreement

    assert disagreement(frozenset(asked), leaning, mode) is to_qwen


@pytest.mark.parametrize(
    ("mode", "leaning", "route"),
    [
        ("off", "other", "student"),
        ("fact", "other", "model"),
        ("fact", "note", "student"),
        ("fact", "none", "student"),
        ("all", "none", "model"),
    ],
)
async def test_cross_check_sends_disagreements_to_qwen(case, mode, leaning, route):
    from dataclasses import replace

    from psychiatry_api.finetune.format import Label, answer

    other = case.facts[1].id
    leaning = other if leaning == "other" else leaning
    model, interpreter = qwen(case, TOPIC | {"asked": [key(case.facts[1].asked_about)]})
    topics, _ = student(answer(case, Label(frozenset({"note"}), "none", "", False, "")), mode)
    rating = replace(UNSURE, leaning=leaning)
    cascade = CascadeInterpreter(Stub(rating), interpreter, {case.id: case}, topics)
    line = "Did you write anything down?"
    assert await cascade.forecast(case, line, history=[]) is (route == "model")
    result, calls, flags = await cascade.interpret(case, DisclosureState(), [], line)
    assert result.topic_route == route and result.topic_leaning == leaning
    if route == "model":
        assert flags == ["student_cross_checked"] and calls[0].status == "cross_checked"
        assert result.asked == {other}
    else:
        assert result.asked == {"note"}
    assert ("cross-check" in cascade.prompt_version) is (mode != "off")


class FakeReranker:
    """Scores like the served reranker: a fixed score per fact ID, in the order asked."""

    def __init__(self, by_fact: dict[str, float] | None, case):
        self.by_fact, self.case, self.sent = by_fact, case, []

    async def score(self, instruction, query, documents):
        from psychiatry_api.models.reranker import RerankReply

        self.sent.append((instruction, query, documents))
        if self.by_fact is None:
            raise ModelError("model_unavailable", "down")
        return RerankReply(tuple(self.by_fact.get(f.id, 0.01) for f in self.case.facts), 120)


def reranker(case, by_fact, **kwargs):
    from psychiatry_api.roleplay.classify import RerankerTopics

    served = {"model": "reranker-test", "weights_sha256": "b" * 64}
    model = FakeReranker(by_fact, case)
    return RerankerTopics(model, served, kwargs.pop("threshold", 0.5), 0.1, **kwargs), model


@pytest.mark.parametrize(
    ("scores", "decision"),
    [
        ({"a": 0.9, "b": 0.2}, {"a"}),
        ({"a": 0.4, "b": 0.2}, set()),  # nothing reaches the threshold: no topic
        ({"a": 0.9, "b": 0.85}, None),  # too close to call: Qwen decides
        ({"a": 0.55, "b": 0.3, "c": 0.5}, None),
        ({}, set()),
    ],
)
def test_reranker_decision_table(scores, decision):
    from psychiatry_api.roleplay.classify import reranked

    result = reranked(scores, 0.5, 0.1)
    assert result == (None if decision is None else frozenset(decision))


async def test_the_reranker_decides_topics_the_classifiers_are_unsure_of(case):
    model, interpreter = qwen(case)  # a Qwen call would fail
    other = case.facts[1].id
    topics, served = reranker(case, {"note": 0.92, other: 0.3})
    cascade = CascadeInterpreter(Stub(UNSURE), interpreter, {case.id: case}, topics)
    history = [("", "Opening."), ("Did anyone find you?", "My flatmate did.")]
    result, calls, flags = await cascade.interpret(case, DisclosureState(), history, "And a note?")
    assert result.asked == {"note"} and result.topic_route == "reranker" and flags == []
    assert calls[0].prompt_version == "rerank-v1" and calls[0].total_ms == 120
    instruction, query, documents = served.sent[0]
    assert "Previous: doctor" in query and query.endswith("Line: And a note?")
    assert len(documents) == len(case.facts) and "Answer:" not in documents[0]
    assert "reranker-test" in cascade.prompt_version


@pytest.mark.parametrize(
    ("scores", "line", "route"),
    [
        ({"note": 0.9, "other": 0.85}, "Did you write anything down?", "model"),  # too close
        ({"note": 0.9}, "You must have left a note.", "model"),  # topic for a statement
        ({"note": 0.1}, "Did you write anything down?", "model"),  # none, classifier leans
        (None, "Did you write anything down?", "model"),  # reranker down
    ],
)
async def test_the_reranker_hands_doubtful_lines_to_qwen(case, scores, line, route):
    from dataclasses import replace

    other = case.facts[1].id
    if scores and "other" in scores:
        scores = {"note": scores["note"], other: scores["other"]}
    model, interpreter = qwen(case, TOPIC | {"asked": [key(case.facts[1].asked_about)]})
    topics, _ = reranker(case, scores)
    rating = replace(UNSURE, leaning=other)
    cascade = CascadeInterpreter(Stub(rating), interpreter, {case.id: case}, topics)
    result, calls, flags = await cascade.interpret(case, DisclosureState(), [], line)
    assert result.topic_route == route and calls[0].status != "completed"


async def test_the_reranker_can_read_each_facts_content(case):
    topics, served = reranker(case, {"note": 0.9}, description="labels_content")
    await topics.topics(case, [], "Did you write anything down?", "note")
    assert all("Answer:" in d for d in served.sent[0][2])
    assert ":labels_content:" in topics.version


async def test_the_reranker_adapter_posts_to_loopback():
    import json

    import httpx

    from psychiatry_api.models.reranker import RerankerModel

    seen = {}

    def handler(request):
        seen["url"], seen["body"] = str(request.url), json.loads(request.content)
        return httpx.Response(200, json={"scores": [0.9, 0.1], "total_ms": 5})

    model = RerankerModel("http://127.0.0.1:8185", "r", 5, httpx.MockTransport(handler))
    reply = await model.score("Judge.", "Line?", ["a", "b"])
    assert reply.scores == (0.9, 0.1) and seen["url"].endswith("/v1/rerank")
    assert seen["body"] == {"instruction": "Judge.", "query": "Line?", "documents": ["a", "b"]}
    with pytest.raises(ModelError):
        RerankerModel("https://example.com", "r", 5)


async def test_training_written_for_another_case_version_is_not_used(tmp_path, caplog):
    """A revised case must not be classified with phrasings for facts it may no longer have."""
    cases = {case.id: case for case in load_cases()}
    root = tmp_path / "training"
    (root / "topics").mkdir(parents=True)
    (root / "tone").mkdir()
    source = Path(TRAINING) / "topics/alcohol-history.yaml"
    current = source.read_text()
    (root / "topics/alcohol-history.yaml").write_text(current)
    stale = current.replace(
        f"case_version: {cases['alcohol-history'].version}", "case_version: 0.0.1"
    ).replace("case_id: alcohol-history", "case_id: memory-collateral-history")
    (root / "topics/memory-collateral-history.yaml").write_text(stale)
    for tone in sorted((Path(TRAINING) / "tone").glob("*.yaml"))[:1]:
        (root / "tone" / tone.name).write_text(tone.read_text())
    classifiers = TrainedClassifiers(FakeEmbeddingModel(dimensions=8), tmp_path / "c.npz", root)
    with caplog.at_level("WARNING"):
        await classifiers.ready(cases)
    assert "alcohol-history" in classifiers.topic
    assert "memory-collateral-history" not in classifiers.topic
    assert classifiers.stale == {"memory-collateral-history": ("0.0.1",)}
    assert "memory-collateral-history" in caplog.text
    rating = await classifiers.rate(cases["memory-collateral-history"], "How is her memory?")
    assert rating.topics is None  # left to the model route
