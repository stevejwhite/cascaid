"""Author-only case editor API under /api/authoring (docs/CASE-EDITOR-PLAN.md).

Mounted only when AUTHORING_ENABLED is set on a development instance; never in a
production profile. These routes return full cases, including withheld facts, so every
request must come from the editor's own host, and every change from its own origin.
"""

import json
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field, field_validator

from psychiatry_api.authoring.checks import CheckResult, check, clean
from psychiatry_api.authoring.drafts import (
    Draft,
    DraftError,
    DraftStore,
    DraftSummary,
    DraftUpdate,
    StoredDraft,
    checked_case,
)
from psychiatry_api.authoring.export import Export, export
from psychiatry_api.authoring.preview import Preview, PreviewRequest, PreviewTurn, preview
from psychiatry_api.cases import (
    BLUEPRINT_VERSION,
    INTERVIEW_SECONDS,
    READING_SECONDS,
    SUBDIVISIONS,
    Case,
    CommunicationFocus,
    Expression,
    Specialty,
    load_cases,
)
from psychiatry_api.config import ROOT, Settings
from psychiatry_api.domain import Contract, NonEmpty
from psychiatry_api.schemas import ErrorResponse

SAFE = frozenset({"GET", "HEAD", "OPTIONS"})


class Choice(Contract):
    value: str | int
    label: str


class AuthoringOptions(Contract):
    """Permitted values, published from the Python schema so the editor cannot drift."""

    blueprint_version: str
    skills: tuple[Choice, ...]
    subdivisions: dict[str, tuple[Choice, ...]]
    specialties: tuple[Choice, ...]
    communication_focus: tuple[Choice, ...]
    reading_seconds: tuple[Choice, ...]
    interview_seconds: int
    roles: tuple[Choice, ...]
    disclosures: tuple[Choice, ...]
    rapport_levels: tuple[Choice, ...]
    indicators: tuple[Choice, ...]
    expressions: tuple[Choice, ...]
    voice_sexes: tuple[Choice, ...]
    voice_ages: tuple[Choice, ...]
    speakers: tuple[Choice, ...]
    avatars: tuple[Choice, ...]
    domains: tuple[str, ...]


class CaseChoice(Contract):
    id: str
    title: str
    version: str


class CreateDraft(Contract):
    author: NonEmpty = Field(max_length=80)
    kind: str = Field(pattern=r"^(new|revision)$", default="new")
    title: str | None = Field(default=None, max_length=160)
    source_case_id: str | None = Field(default=None, max_length=60)


class CaseBody(Contract):
    case: dict[str, Any]

    _case = field_validator("case")(checked_case)


class PreviewBody(CaseBody):
    turns: tuple[PreviewTurn, ...] = Field(default=(), max_length=40)


class ExportBody(Contract):
    revision: int = Field(ge=1)


def label(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").capitalize()


def choices(values) -> tuple[Choice, ...]:
    return tuple(Choice(value=v, label=label(str(v))) for v in values)


def literal_values(kind) -> tuple[str, ...]:
    return kind.__args__


def options(settings: Settings) -> AuthoringOptions:
    tts = json.loads((ROOT / "config/tts-runtime.json").read_text())
    avatars = json.loads((ROOT / "config/avatar-register.json").read_text())
    cases = load_cases(settings.cases_path)
    return AuthoringOptions(
        blueprint_version=BLUEPRINT_VERSION,
        skills=choices(skill.value for skill in SUBDIVISIONS),
        subdivisions={skill.value: choices(sorted(s)) for skill, s in SUBDIVISIONS.items()},
        specialties=choices(literal_values(Specialty)),
        communication_focus=choices(literal_values(CommunicationFocus)),
        reading_seconds=tuple(
            Choice(value=s, label=f"{s // 60} minutes" if s >= 120 else f"{s} seconds")
            for s in sorted(READING_SECONDS)
        ),
        interview_seconds=INTERVIEW_SECONDS,
        roles=choices(("patient", "relative", "carer", "colleague")),
        disclosures=(
            Choice(value="volunteered", label="Can be volunteered"),
            Choice(value="on_direct_question", label="Share when asked"),
            Choice(value="after_rapport", label="Share when asked after rapport"),
        ),
        rapport_levels=(
            Choice(value=1, label="Level 1: one brief empathic remark"),
            Choice(value=2, label="Level 2: specific empathy, or two brief remarks close together"),
        ),
        indicators=choices(("summary", "check_understanding", "empathy", "open_question")),
        expressions=choices(literal_values(Expression)),
        voice_sexes=choices(("female", "male")),
        voice_ages=choices(("young", "adult", "older")),
        speakers=tuple(
            Choice(value=v["name"], label=f"{v['name']} ({v['description']})")
            for v in tts["voices"]
        ),
        avatars=tuple(
            Choice(value=a["id"], label=f"{a['id']} ({a['sex']}, {a['apparent_age']})")
            for a in avatars["avatars"]
        ),
        domains=tuple(
            sorted(
                {f.domain for c in cases for f in c.facts}
                | {t.domain for c in cases for t in c.tasks}
            )
        ),
    )


def guard(settings: Settings):
    allowed = {o.strip().rstrip("/") for o in settings.authoring_origins.split(",") if o.strip()}
    hosts = {urlparse(origin).netloc for origin in allowed}
    hosts |= {f"127.0.0.1:{settings.api_port}", f"localhost:{settings.api_port}"}

    def check_request(request: Request) -> None:
        # Through the web proxy the browser's host arrives as x-forwarded-host.
        host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
        if host not in hosts:
            raise HTTPException(403, "The case editor is available only from this machine")
        if request.method not in SAFE and request.headers.get("origin") not in allowed:
            raise HTTPException(403, "Cross-site request refused")

    return check_request


def authoring_router(settings: Settings) -> APIRouter:
    assert settings.authoring_enabled and not settings.production
    router = APIRouter(
        prefix="/api/authoring",
        tags=["Case authoring"],
        dependencies=[Depends(guard(settings))],
        responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    store = DraftStore(settings.authoring_path, settings.cases_path)

    def handled(work):
        try:
            return work()
        except DraftError as error:
            raise HTTPException(error.status, error.detail) from error

    def context(draft: StoredDraft) -> dict:
        taken: set[str] = set()
        if draft.kind == "new":
            # Active cases and other new drafts; a revision keeps its own active ID.
            taken = {case.id for case in load_cases(settings.cases_path)}
            taken |= {
                d.case_id for d in store.list() if d.kind == "new" and d.draft_id != draft.draft_id
            }
        return {
            "taken_ids": taken,
            "source_version": draft.source.version if draft.source else None,
            "revision": draft.kind == "revision",
        }

    def valid(draft: StoredDraft, case: dict) -> Case:
        result = check(case, **context(draft))
        if not result.valid:
            raise HTTPException(
                422,
                "Fix the case's errors first: " + "; ".join(e.message for e in result.errors[:3]),
            )
        return Case.model_validate(clean(case))

    @router.get("/options", response_model=AuthoringOptions)
    def get_options() -> AuthoringOptions:
        return options(settings)

    @router.get("/cases", response_model=tuple[CaseChoice, ...])
    def cases() -> tuple[CaseChoice, ...]:
        return tuple(
            CaseChoice(id=c.id, title=c.title, version=c.version)
            for c in load_cases(settings.cases_path)
        )

    @router.get("/drafts", response_model=tuple[DraftSummary, ...])
    def drafts() -> tuple[DraftSummary, ...]:
        return tuple(store.list())

    @router.post("/drafts", response_model=Draft, responses={422: {"model": ErrorResponse}})
    def create(body: CreateDraft) -> Draft:
        return handled(
            lambda: store.create(
                body.author,
                body.title,
                body.source_case_id,
                body.kind,  # type: ignore[arg-type]
            )
        ).public()

    @router.get("/drafts/{draft_id}", response_model=Draft)
    def read(draft_id: str) -> Draft:
        return handled(lambda: store.load(draft_id)).public()

    @router.put(
        "/drafts/{draft_id}", response_model=Draft, responses={409: {"model": ErrorResponse}}
    )
    def save(draft_id: str, body: DraftUpdate) -> Draft:
        return handled(lambda: store.save(draft_id, body)).public()

    @router.post("/drafts/{draft_id}/check", response_model=CheckResult)
    def check_draft(draft_id: str, body: CaseBody) -> CheckResult:
        draft = handled(lambda: store.load(draft_id))
        return check(body.case, **context(draft))

    @router.post(
        "/drafts/{draft_id}/preview",
        response_model=Preview,
        responses={422: {"model": ErrorResponse}},
    )
    def preview_draft(draft_id: str, body: PreviewBody) -> Preview:
        draft = handled(lambda: store.load(draft_id))
        return preview(valid(draft, body.case), PreviewRequest(turns=body.turns))

    @router.post(
        "/drafts/{draft_id}/export",
        response_model=Export,
        responses={409: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def export_draft(draft_id: str, body: ExportBody) -> Export:
        draft = handled(lambda: store.load(draft_id))
        if body.revision != draft.revision:
            raise HTTPException(409, "Save the draft before exporting it")
        case = valid(draft, draft.case)
        return export(draft, case, settings.cases_path, settings.authoring_path)

    return router
