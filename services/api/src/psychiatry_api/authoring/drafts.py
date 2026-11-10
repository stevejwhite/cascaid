"""Case drafts: saved incomplete, never read by the learner case loader.

A draft holds the case as plain JSON (the same shape as a case file), the source file's
text when it revises or copies an existing case, and the author's notes. Drafts live in
their own directory, addressed by server-assigned IDs, written atomically. A save must name
the revision it edited; a stale save is refused rather than overwriting newer work.
"""

import hashlib
import json
import os
import re
import tempfile
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import AwareDatetime, Field, field_validator

from psychiatry_api.authoring.yaml_io import plain, slug
from psychiatry_api.cases import BLUEPRINT_SOURCE_ID, BLUEPRINT_VERSION, Case, load_cases
from psychiatry_api.domain import Contract

DRAFT_ID = re.compile(r"^[0-9a-f]{32}$")
MAX_CASE_BYTES = 256 * 1024
CASE_FIELDS = frozenset(Case.model_fields)


class DraftError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


class DraftSource(Contract):
    case_id: str
    version: str
    sha256: str


def checked_case(value: dict[str, Any]) -> dict[str, Any]:
    """A relaxed draft may be incomplete, but only in the shape of a case and bounded."""
    unknown = set(value) - CASE_FIELDS
    if unknown:
        raise ValueError(f"Unknown case fields: {', '.join(sorted(unknown))}")
    if len(json.dumps(value)) > MAX_CASE_BYTES:
        raise ValueError("The draft case is too large")
    return value


class DraftContent(Contract):
    """What the author edits."""

    case: dict[str, Any]
    notes: str = Field(default="", max_length=20_000)
    objectives: str = Field(default="", max_length=5_000)

    _case = field_validator("case")(checked_case)


class DraftUpdate(DraftContent):
    # The revision this edit started from; a different stored revision is a conflict.
    revision: int = Field(ge=1)


class DraftSummary(Contract):
    draft_id: str
    revision: int
    title: str
    case_id: str
    kind: Literal["new", "revision"]
    source: DraftSource | None
    author: str
    updated_at: AwareDatetime


class Draft(DraftContent):
    draft_id: str
    revision: int
    kind: Literal["new", "revision"]
    source: DraftSource | None
    author: str
    created_at: AwareDatetime
    updated_at: AwareDatetime

    def summary(self) -> DraftSummary:
        return DraftSummary(
            draft_id=self.draft_id,
            revision=self.revision,
            title=str(self.case.get("title") or "Untitled case"),
            case_id=str(self.case.get("id") or ""),
            kind=self.kind,
            source=self.source,
            author=self.author,
            updated_at=self.updated_at,
        )


class StoredDraft(Draft):
    # The source case file's text, kept for recovery and for merging comments on export.
    source_text: str | None = None

    def public(self) -> Draft:
        return Draft.model_validate(self.model_dump(exclude={"source_text"}))


def now() -> datetime:
    return datetime.now(UTC)


def next_minor(version: str) -> str:
    major, minor, _ = (int(part) for part in version.split("."))
    return f"{major}.{minor + 1}.0"


def blank_case(case_id: str, title: str, author: str) -> dict[str, Any]:
    """A new case with the permitted defaults and empty required text."""
    return {
        "id": case_id,
        "version": "0.1.0",
        "title": title,
        "blueprint": {
            "skill": "history",
            "subdivision": "presenting_complaint_and_psychiatric_history",
            "specialty": "general",
            "communication_focus": [],
        },
        "timing": {"reading_seconds": 90},
        "authorship": {"author": author, "status": "author_draft"},
        "candidate_instructions": "",
        "persona": {
            "role": "patient",
            "name": "",
            "description": "",
            "speech_style": "",
            "affect": "",
            "opening_statement": "",
        },
        "facts": [],
        "tasks": [],
        "unscripted_response": "",
    }


class DraftStore:
    def __init__(self, root: Path, cases_path: Path) -> None:
        self.root = root / "drafts"
        self.cases_path = cases_path
        # Revision checks and writes happen together, even with concurrent requests.
        self.lock = threading.Lock()

    def _file(self, draft_id: str) -> Path:
        if not DRAFT_ID.fullmatch(draft_id):
            raise DraftError(404, "Draft not found")
        return self.root / f"{draft_id}.json"

    def _write(self, draft: StoredDraft) -> None:
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        handle, temporary = tempfile.mkstemp(dir=self.root, suffix=".tmp")
        try:
            with os.fdopen(handle, "w") as out:
                out.write(draft.model_dump_json(indent=2))
            os.replace(temporary, self._file(draft.draft_id))
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise

    def load(self, draft_id: str) -> StoredDraft:
        file = self._file(draft_id)
        if not file.exists():
            raise DraftError(404, "Draft not found")
        return StoredDraft.model_validate_json(file.read_text())

    def list(self) -> list[DraftSummary]:
        if not self.root.exists():
            return []
        drafts = [self.load(file.stem).summary() for file in self.root.glob("*.json")]
        return sorted(drafts, key=lambda d: d.updated_at, reverse=True)

    def taken_ids(self) -> set[str]:
        ids = {case.id for case in load_cases(self.cases_path)}
        return ids | {d.case_id for d in self.list() if d.kind == "new"}

    def create(
        self,
        author: str,
        title: str | None = None,
        source_id: str | None = None,
        kind: Literal["new", "revision"] = "new",
    ) -> StoredDraft:
        source = source_text = None
        if source_id is not None:
            file = self.cases_path / f"{source_id}.yaml"
            if not re.fullmatch(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", source_id) or not file.exists():
                raise DraftError(404, "Station case not found")
            source_text = file.read_text()
            case = plain(source_text)
            source = DraftSource(
                case_id=source_id,
                version=case["version"],
                sha256=hashlib.sha256(source_text.encode()).hexdigest(),
            )
            if kind == "revision":
                case["version"] = next_minor(case["version"])
            else:
                title = title or f"{case['title']} (copy)"
                case["id"] = slug(title, self.taken_ids())
                case["title"] = title
                case["version"] = "0.1.0"
        else:
            if kind == "revision":
                raise DraftError(422, "A revision needs a source case")
            title = (title or "").strip() or "Untitled case"
            case = blank_case(slug(title, self.taken_ids()), title, author)
        # Edited or copied content is an author draft again, whatever its source status.
        case.setdefault("authorship", {"author": author})["status"] = "author_draft"
        case["authorship"].pop("clinically_validated", None)
        blueprint = case.setdefault("blueprint", {})
        if (
            blueprint.get("source_id", BLUEPRINT_SOURCE_ID) != BLUEPRINT_SOURCE_ID
            or blueprint.get("version", BLUEPRINT_VERSION) != BLUEPRINT_VERSION
        ):
            raise DraftError(422, "The source case targets another blueprint version")
        moment = now()
        draft = StoredDraft(
            draft_id=uuid.uuid4().hex,
            revision=1,
            kind=kind,
            source=source,
            author=author,
            created_at=moment,
            updated_at=moment,
            case=checked_case(case),
            source_text=source_text,
        )
        self._write(draft)
        return draft

    def save(self, draft_id: str, update: DraftUpdate) -> StoredDraft:
        with self.lock:
            return self._save(draft_id, update)

    def _save(self, draft_id: str, update: DraftUpdate) -> StoredDraft:
        current = self.load(draft_id)
        if update.revision != current.revision:
            raise DraftError(
                409,
                f"This draft was saved elsewhere (revision {current.revision}); reload it "
                "before saving so newer changes are not overwritten.",
            )
        if current.kind == "revision" and update.case.get("id") != current.case.get("id"):
            raise DraftError(422, "A revision keeps its case ID")
        if current.kind == "new" and update.case.get("id") != current.case.get("id"):
            raise DraftError(422, "The case ID is fixed when the draft is created")
        saved = current.model_copy(
            update={
                "case": update.case,
                "notes": update.notes,
                "objectives": update.objectives,
                "revision": current.revision + 1,
                "updated_at": now(),
            }
        )
        self._write(saved)
        return saved
