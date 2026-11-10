import json

import pytest
from fastapi.testclient import TestClient

from psychiatry_api.cases import CASES_PATH, load_case
from psychiatry_api.main import create_app
from psychiatry_api.models.contracts import GenerationRequest, TextDelta, TextOutput
from psychiatry_api.models.fakes import FakeLanguageModel
from psychiatry_api.roleplay.disclosure import Disclosure, DisclosureState
from psychiatry_api.roleplay.respond import (
    said_before,
    split_sentences,
    stated_numbers,
    stream_reply,
)


@pytest.fixture
def case():
    return load_case(CASES_PATH / "overdose-risk-assessment.yaml")


async def run(case, text, finish="stop", said=frozenset(), allowed=None):
    model = FakeLanguageModel([TextOutput(text=text)])
    request = GenerationRequest.model_validate(
        {"messages": [{"role": "user", "content": "x"}], "options": {"promptVersion": "t"}}
    )

    async def events():
        async for event in model.stream(request):
            if isinstance(event, TextDelta):
                yield event
            else:
                meta = event.metadata.model_copy(update={"finish_reason": finish})
                yield event.model_copy(update={"metadata": meta})

    released, done = [], None
    async for kind, payload in stream_reply(case, events(), 3, "t", [], said, allowed):
        if kind == "sentence":
            released.append(payload)
        else:
            done = payload
    return released, done


def test_sentence_splitting_keeps_the_unfinished_remainder():
    assert split_sentences("Hi there. I took them! Then I") == (
        ["Hi there.", "I took them!"],
        "Then I",
    )


async def test_the_guarded_reply_is_released_sentence_by_sentence(case):
    released, (reply, calls, flags) = await run(
        case, "*sighs* I took them. I just want to go home."
    )
    assert released == ["I took them.", "I just want to go home."]
    assert reply == "I took them. I just want to go home." and flags == ["cleaned"]
    assert calls[0].status == "completed"


async def test_a_character_break_anywhere_replaces_the_whole_reply(case):
    released, (reply, _, flags) = await run(
        case, "I took them. As an AI I can share the case. My mum matters."
    )
    assert reply in {case.unscripted_response, *case.deflections} and " ".join(released) == reply
    assert flags == ["character_break", "deflected"]


async def test_a_stage_direction_spanning_sentences_is_removed(case):
    _, (reply, _, flags) = await run(case, "I took them. *looks away. sighs* I'm tired.")
    assert reply == "I took them. I'm tired." and "cleaned" in flags


async def test_an_unfinished_last_sentence_is_dropped_not_trimmed(case):
    released, (_, _, flags) = await run(case, "I took twenty. Then I went to", finish="length")
    assert released == ["I took twenty."] and "truncated" in flags


async def test_a_sentence_already_said_is_dropped_unless_it_opens_the_reply(case):
    said = said_before([("", "I just want to go home.")])
    _, (reply, _, flags) = await run(case, "I took twenty. I just want to go home!", said=said)
    assert reply == "I took twenty." and flags == ["repeat_dropped"]
    _, (reply, _, flags) = await run(case, "I just want to go home.", said=said)
    assert reply == "I just want to go home." and flags == []


async def test_a_sentence_with_an_unsupported_number_is_dropped(case):
    _, (reply, _, flags) = await run(
        case, "I took twenty tablets. It was about two years ago.", allowed={20}
    )
    assert reply == "I took twenty tablets." and flags == ["number_dropped"]
    _, (reply, _, flags) = await run(case, "It started two years ago.", allowed={20})
    assert reply in {case.unscripted_response, *case.deflections}
    assert flags == ["number_dropped", "deflected"]


def test_stated_numbers_come_from_known_facts_persona_and_question(case):
    state = DisclosureState(unlocked=("overdose-details",))
    allowed = stated_numbers(case, Disclosure(state=state), "Was it three days ago?")
    assert {20, 11, 34, 3} <= allowed and 2 not in allowed


def ndjson(response):
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_stream_endpoint_sends_sentences_then_the_session(settings, tmp_path):
    app = create_app(settings.model_copy(update={"sessions_path": tmp_path}))
    with TestClient(app) as client:
        sid = client.post("/api/sessions", json={"case_id": "elevated-mood-history"}).json()
        sid = sid["session_id"]
        early = ndjson(client.post(f"/api/sessions/{sid}/turns/stream", json={"text": "Hi"}))
        assert early == [
            {"type": "error", "status": 409, "detail": "Begin the interview before speaking"}
        ]
        client.post(f"/api/sessions/{sid}/begin")
        events = ndjson(
            client.post(f"/api/sessions/{sid}/turns/stream", json={"text": "How is your sleep?"})
        )
        # The keyword stand-in never waits for a language model: pace says so first.
        assert [e["type"] for e in events] == ["pace", "sentence", "done"]
        assert events[0] == {"type": "pace", "slow": False}
        events = events[1:]
        assert "three hours a night" in events[0]["text"]
        assert events[-1]["session"]["transcript"][-1]["text"] == events[0]["text"]
    turn = [json.loads(line) for line in (tmp_path / f"{sid}.jsonl").read_text().splitlines()][-1]
    assert turn["type"] == "turn" and turn["first_sentence_ms"] is not None
