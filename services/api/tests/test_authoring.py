"""Case editor: drafts, checks, rule preview, export and the author-only boundary."""

import random
import shutil

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from psychiatry_api.authoring.checks import check
from psychiatry_api.authoring.drafts import DraftError, DraftStore, DraftUpdate
from psychiatry_api.authoring.preview import PreviewRequest, PreviewTurn, preview
from psychiatry_api.authoring.yaml_io import plain, render, slug
from psychiatry_api.cases import CASES_PATH, Case, load_cases
from psychiatry_api.config import Settings
from psychiatry_api.main import create_app
from psychiatry_api.roleplay.disclosure import DisclosureState, Interpretation, apply, known

ORIGIN = "http://testserver"


@pytest.fixture
def cases_dir(tmp_path):
    target = tmp_path / "cases"
    shutil.copytree(CASES_PATH, target)
    return target


@pytest.fixture
def settings(tmp_path, cases_dir):
    return Settings(
        _env_file=None,
        model_backend="fake",
        cases_path=cases_dir,
        sessions_path=tmp_path / "sessions",
        authoring_enabled=True,
        authoring_path=tmp_path / "authoring",
        authoring_origins=ORIGIN,
    )


@pytest.fixture
def client(settings):
    return TestClient(create_app(settings), headers={"Origin": ORIGIN})


@pytest.fixture
def store(settings):
    return DraftStore(settings.authoring_path, settings.cases_path)


def minimal_case(**changes) -> dict:
    case = {
        "id": "test-case",
        "version": "0.1.0",
        "title": "Test case",
        "blueprint": {
            "skill": "history",
            "subdivision": "presenting_complaint_and_psychiatric_history",
            "specialty": "general",
        },
        "timing": {"reading_seconds": 90},
        "authorship": {"author": "Tester", "status": "author_draft"},
        "candidate_instructions": "Take a history from Sam, aged 40.",
        "persona": {
            "role": "patient",
            "name": "Sam",
            "age": 40,
            "description": "Lives alone.",
            "speech_style": "Brief.",
            "affect": "Guarded.",
            "opening_statement": "I'm not sure why I'm here.",
        },
        "facts": [
            {
                "id": "mood",
                "content": "I feel low.",
                "disclosure": "volunteered",
                "asked_about": ["mood", "feelings"],
                "domain": "mood",
            },
            {
                "id": "sleep",
                "content": "I wake at four every morning.",
                "vague": "I don't sleep well.",
                "disclosure": "on_direct_question",
                "asked_about": ["sleep", "waking"],
                "domain": "mood",
                "key": True,
            },
            {
                "id": "plans",
                "content": "I have thought about ending my life.",
                "disclosure": "after_rapport",
                "rapport_needed": 2,
                "asked_about": ["suicidal thoughts", "harming yourself"],
                "domain": "risk",
                "key": True,
            },
        ],
        "tasks": [
            {
                "id": "ask-risk",
                "description": "Ask about risk",
                "domain": "risk",
                "evidence_fact": "plans",
            }
        ],
        "unscripted_response": "I'd rather not say.",
        "affect_stages": [
            {"id": "guarded", "affect": "Guarded"},
            {"id": "open", "affect": "More open", "rapport_at_least": 1},
            {"id": "defensive", "affect": "Defensive", "on_confrontation": True},
        ],
        "questions": [{"id": "ask-help", "text": "Can anything help?", "after_fact": "sleep"}],
    }
    case.update(changes)
    return case


# Drafts


def test_new_copy_and_revision_drafts(store):
    blank = store.create("Dr A", title="Low mood in a farmer")
    assert blank.case["id"] == "low-mood-in-a-farmer"
    assert blank.case["version"] == "0.1.0" and blank.kind == "new"
    again = store.create("Dr A", title="Low mood in a farmer")
    assert again.case["id"] == "low-mood-in-a-farmer-2"  # collision-checked

    copy = store.create("Dr B", source_id="alcohol-history")
    assert copy.case["id"] == "alcohol-use-history-copy"
    assert copy.case["version"] == "0.1.0" and copy.kind == "new"
    assert copy.source.case_id == "alcohol-history" and len(copy.source.sha256) == 64

    revision = store.create("Dr B", source_id="alcohol-history", kind="revision")
    source = next(c for c in load_cases() if c.id == "alcohol-history")
    major, minor, _ = source.version.split(".")
    assert revision.case["id"] == "alcohol-history"
    assert revision.case["version"] == f"{major}.{int(minor) + 1}.0"
    assert revision.case["authorship"]["status"] == "author_draft"
    assert revision.source_text.startswith("# ")


def test_incomplete_drafts_save_and_reopen(store):
    draft = store.create("Dr A", title="Work in progress")
    case = dict(draft.case, candidate_instructions="Half written")
    saved = store.save(draft.draft_id, DraftUpdate(revision=1, case=case, notes="To do"))
    reopened = store.load(draft.draft_id)
    assert reopened.revision == 2 == saved.revision
    assert reopened.case["candidate_instructions"] == "Half written"
    assert reopened.notes == "To do"
    assert [d.draft_id for d in store.list()] == [draft.draft_id]


def test_stale_saves_are_refused(store):
    draft = store.create("Dr A", title="Conflict")
    store.save(draft.draft_id, DraftUpdate(revision=1, case=draft.case))
    with pytest.raises(DraftError) as error:
        store.save(draft.draft_id, DraftUpdate(revision=1, case=draft.case))
    assert error.value.status == 409


def test_ids_are_fixed_and_drafts_addressed_only_by_id(store):
    draft = store.create("Dr A", title="Fixed")
    with pytest.raises(DraftError):
        store.save(draft.draft_id, DraftUpdate(revision=1, case=dict(draft.case, id="other")))
    for bad in ("../../etc/passwd", "ABC", "0" * 31):
        with pytest.raises(DraftError) as error:
            store.load(bad)
        assert error.value.status == 404
    with pytest.raises(DraftError):
        store.create("Dr A", source_id="../cases/alcohol-history")


def test_unknown_fields_and_oversized_drafts_are_rejected():
    with pytest.raises(ValidationError):
        DraftUpdate(revision=1, case={"id": "x", "executable": "!!python/object"})
    with pytest.raises(ValidationError):
        DraftUpdate(revision=1, case={"title": "x" * 300_000})


def test_slugs_are_stable_and_collision_checked():
    assert slug("Alcohol use — history", set()) == "alcohol-use-history"
    assert slug("A", {"a", "a-2"}) == "a-3"
    assert slug("!!!", set()) == "item"


# Checks


def test_schema_errors_point_at_their_fields():
    case = minimal_case()
    case["facts"][0]["vague"] = "Something"  # not allowed on a volunteered fact
    case["persona"]["name"] = ""
    del case["unscripted_response"]
    result = check(case, taken_ids=set(), source_version=None, revision=False)
    assert not result.valid
    locs = {e.loc for e in result.errors}
    assert ("persona", "name") in locs
    assert ("unscripted_response",) in locs
    assert any("volunteered fact cannot have a vague version" in e.message for e in result.errors)


def test_broken_references_and_collisions_block_export():
    case = minimal_case()
    case["tasks"][0]["evidence_fact"] = "removed"
    result = check(case, taken_ids={"test-case"}, source_version=None, revision=False)
    messages = " ".join(e.message for e in result.errors)
    assert "links unknown fact removed" in messages
    assert "Another case already uses this ID" in messages


def test_revisions_need_a_higher_version():
    result = check(minimal_case(), taken_ids=set(), source_version="0.1.0", revision=True)
    assert [e.loc for e in result.errors] == [("version",)]
    assert check(
        minimal_case(version="0.2.0"), taken_ids=set(), source_version="0.1.0", revision=True
    ).valid


def test_review_prompts_say_what_they_checked():
    case = minimal_case(candidate_instructions="Take a history from Sam, aged 42.")
    case["persona"]["opening_statement"] = "I have thought about ending everything in my life."
    case["facts"][1]["asked_about"] = ["mood"]
    result = check(case, taken_ids=set(), source_version=None, revision=False)
    assert result.valid
    messages = [p.message for p in result.prompts]
    assert any("plans" in m and "from the start" in m for m in messages)
    assert any("also used by" in m for m in messages)
    assert any("one question label" in m for m in messages)
    assert any("States age 42" in m for m in messages)
    assert all(p.checked for p in result.prompts)


# Rule preview


def test_preview_explains_rapport_vague_answers_and_confrontation():
    case = Case.model_validate(minimal_case())
    turns = [
        PreviewTurn(asked=("plans",)),  # early sensitive question
        PreviewTurn(asked=("sleep",)),  # vague first
        PreviewTurn(asked=("sleep",), empathy=2),  # full answer, rapport rises
        PreviewTurn(asked=("plans",)),  # 1.6 >= 1.5 after decay
        PreviewTurn(confrontational=True),
    ]
    result = preview(case, PreviewRequest(turns=tuple(turns)))
    outcome = [[(o.fact_id, o.result) for o in step.outcomes] for step in result.steps]
    assert outcome[0] == [("plans", "held_back")]
    assert "rapport level 2" in result.steps[0].outcomes[0].reason
    assert outcome[1] == [("sleep", "partial")]
    sleep = next(f for f in result.steps[1].facts if f.fact_id == "sleep")
    assert sleep.state == "partial" and sleep.permitted_text == "I don't sleep well."
    assert result.steps[1].character_question == "Can anything help?"
    assert outcome[2] == [("sleep", "released")]
    assert "after the vague answer" in result.steps[2].outcomes[0].reason
    assert outcome[3] == [("plans", "released")]
    assert result.steps[3].affect_stage == "open"
    assert result.steps[4].affect_stage == "defensive"
    assert [g.title for g in result.groups][0] == "Available from the start"
    assert "not tested" in result.label


@pytest.mark.parametrize("seed", range(5))
def test_preview_matches_the_production_rules_on_every_case(seed):
    rng = random.Random(seed)
    for case in load_cases():
        ids = [f.id for f in case.facts] + ["unknown"]
        turns = tuple(
            PreviewTurn(
                asked=tuple(rng.sample(ids, rng.randint(0, 2))),
                empathy=rng.choice((0, 0, 1, 2)),
                confrontational=rng.random() < 0.15,
            )
            for _ in range(8)
        )
        result = preview(case, PreviewRequest(turns=turns))
        state = DisclosureState()
        for turn, step in zip(turns, result.steps, strict=True):
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
            got = {o.fact_id: o.result for o in step.outcomes}
            assert {f for f, r in got.items() if r == "held_back"} == set(disclosure.deferred)
            assert {f for f, r in got.items() if r == "partial"} == set(disclosure.touched)
            assert {f for f, r in got.items() if r == "released"} == set(disclosure.unlocked)
            assert step.rapport == state.rapport
            assert step.affect_stage == (disclosure.stage.id if disclosure.stage else None)
            permitted = {f.fact_id: f.permitted_text for f in step.facts if f.permitted_text}
            assert permitted == {f.id: f.content for f in known(case, state)}


# Export


def test_unchanged_revision_keeps_every_comment(store, settings):
    from psychiatry_api.authoring.export import export

    draft = store.create("Dr A", source_id="amputation-refusal-capacity", kind="revision")
    case = Case.model_validate(draft.case)
    result = export(draft, case, settings.cases_path, settings.authoring_path)
    source = (settings.cases_path / "amputation-refusal-capacity.yaml").read_text()
    assert result.dropped_comments == ()
    assert result.case_yaml.splitlines()[:7] == source.splitlines()[:7]
    assert plain(result.case_yaml) == draft.case
    assert "## Before this case can be used for practice" in result.review_markdown
    assert "topic training" in result.review_markdown.lower()
    # The active case is untouched; the export lands in the authoring directory.
    assert (settings.cases_path / "amputation-refusal-capacity.yaml").read_text() == source
    assert (settings.authoring_path / "exports").exists()


def test_comments_on_removed_items_are_reported(tmp_path):
    source = (
        (CASES_PATH / "alcohol-history.yaml")
        .read_text()
        .replace(
            "  - id: tolerance\n",
            "  # Reviewer: tolerance wording agreed with Dr X\n  - id: tolerance\n",
        )
    )
    case = plain(source)
    case["facts"] = [f for f in case["facts"] if f["id"] != "tolerance"]
    _, dropped = render(case, source)
    assert dropped == ["# Reviewer: tolerance wording agreed with Dr X"]
    kept, none = render(plain(source), source)
    assert none == [] and "tolerance wording agreed" in kept


def test_new_cases_get_the_honest_header():
    text, dropped = render(minimal_case(), None)
    assert text.startswith("# Original fictional case")
    assert "Not clinically validated." in text.splitlines()[1]
    assert dropped == []


# API and boundary


def test_author_flow_through_the_api(client, settings):
    created = client.post(
        "/api/authoring/drafts",
        json={"author": "Dr A", "kind": "revision", "source_case_id": "alcohol-history"},
    ).json()
    draft_id = created["draft_id"]
    case = created["case"]
    case["facts"][0]["content"] = "About a litre of vodka a day now."
    saved = client.put(
        f"/api/authoring/drafts/{draft_id}",
        json={"revision": 1, "case": case, "notes": "", "objectives": ""},
    )
    assert saved.status_code == 200 and saved.json()["revision"] == 2
    stale = client.put(
        f"/api/authoring/drafts/{draft_id}",
        json={"revision": 1, "case": case, "notes": "", "objectives": ""},
    )
    assert stale.status_code == 409
    checked = client.post(f"/api/authoring/drafts/{draft_id}/check", json={"case": case}).json()
    assert checked["valid"] is True
    previewed = client.post(
        f"/api/authoring/drafts/{draft_id}/preview",
        json={"case": case, "turns": [{"asked": ["quantity"]}]},
    ).json()
    assert previewed["steps"][0]["outcomes"][0]["fact_id"] == "quantity"
    assert (
        client.post(f"/api/authoring/drafts/{draft_id}/export", json={"revision": 1}).status_code
        == 409
    )
    exported = client.post(f"/api/authoring/drafts/{draft_id}/export", json={"revision": 2}).json()
    assert "About a litre of vodka a day now." in exported["case_yaml"]
    assert "facts: `quantity` changed (content)" in exported["review_markdown"]
    assert exported["source_changed"] is False
    # The learner station list is unchanged and never lists drafts.
    stations = client.get("/api/cases").json()
    assert len(stations) == len(load_cases(settings.cases_path))
    assert "facts" not in stations[0]
    options = client.get("/api/authoring/options").json()
    assert options["reading_seconds"][0]["value"] == 90
    assert "presenting_complaint_and_psychiatric_history" in [
        c["value"] for c in options["subdivisions"]["history"]
    ]


def test_invalid_drafts_cannot_be_previewed_or_exported(client):
    created = client.post("/api/authoring/drafts", json={"author": "Dr A", "title": "Empty"}).json()
    draft_id = created["draft_id"]
    assert (
        client.post(
            f"/api/authoring/drafts/{draft_id}/preview", json={"case": created["case"], "turns": []}
        ).status_code
        == 422
    )
    assert (
        client.post(f"/api/authoring/drafts/{draft_id}/export", json={"revision": 1}).status_code
        == 422
    )


def test_editor_requires_its_own_host_and_origin(settings):
    app = create_app(settings)
    assert TestClient(app).get("/api/authoring/drafts").status_code == 200
    foreign_host = TestClient(app, base_url="http://evil.example")
    assert foreign_host.get("/api/authoring/drafts").status_code == 403
    rebound = TestClient(app, headers={"X-Forwarded-Host": "evil.example"})
    assert rebound.get("/api/authoring/cases").status_code == 403
    for origin in (None, "https://evil.example"):
        headers = {"Origin": origin} if origin else {}
        response = TestClient(app, headers=headers).post(
            "/api/authoring/drafts", json={"author": "x", "title": "y"}
        )
        assert response.status_code == 403


def test_editor_is_absent_unless_enabled(settings):
    off = settings.model_copy(update={"authoring_enabled": False})
    assert TestClient(create_app(off)).get("/api/authoring/drafts").status_code == 404


def test_editor_is_never_available_in_production(tmp_path):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            deployment_profile="production-local",
            model_backend="local",
            speech_backend="local",
            tts_backend="local",
            student_backend="local",
            sessions_path=tmp_path / "s",
            classifier_cache=tmp_path / "c",
            authoring_enabled=True,
        )


def test_owner_sign_in_does_not_reach_the_editor_online(tmp_path):
    """Even a verified owner assertion through the tunnel finds no authoring routes."""
    import httpx

    from psychiatry_api.access import AccessVerifier
    from tests.test_access import ORIGIN as PUBLIC
    from tests.test_access import Keys, online, signed

    settings = online(tmp_path)
    verifier = AccessVerifier.of(settings, transport=httpx.MockTransport(Keys().handler))
    client = TestClient(create_app(settings, verifier))
    assert client.get("/api/cases", headers=signed()).status_code == 200
    for method, path in (
        ("get", "/api/authoring/drafts"),
        ("get", "/api/authoring/options"),
        ("post", "/api/authoring/drafts"),
    ):
        response = getattr(client, method)(path, headers=signed() | {"Origin": PUBLIC})
        assert response.status_code == 404


def test_every_shipped_case_round_trips_with_its_comments():
    for path in sorted(CASES_PATH.glob("*.yaml")):
        source = path.read_text()
        text, dropped = render(plain(source), source)
        assert dropped == [], path.name
        assert plain(text) == plain(source), path.name
