"""Export a checked draft as a case file plus a human-readable review sheet.

Export never touches data/cases. It writes to the authoring exports directory for a
developer to integrate through the station process (docs/CASE-EDITOR-PLAN.md, "From export
to practice"). The exported case is always an author draft and never clinically validated.
"""

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import yaml

from psychiatry_api.authoring.checks import clean, prompts
from psychiatry_api.authoring.drafts import StoredDraft
from psychiatry_api.authoring.yaml_io import plain, render
from psychiatry_api.cases import Case
from psychiatry_api.config import ROOT
from psychiatry_api.domain import Contract


class Export(Contract):
    # The checked case exactly as exported.
    case: Case
    file_name: str
    case_yaml: str
    review_markdown: str
    dropped_comments: tuple[str, ...]
    source_changed: bool
    saved_to: str


def _by_id(items: list[dict]) -> dict[str, dict]:
    return {item["id"]: item for item in items if isinstance(item, dict) and "id" in item}


def changes(before: dict | None, after: dict) -> list[str]:
    if before is None:
        return ["New case."]
    lines = []
    for key in after.keys() | before.keys():
        if key in ("facts", "tasks", "questions", "affect_stages"):
            old, new = _by_id(before.get(key, [])), _by_id(after.get(key, []))
            for item_id in new.keys() - old.keys():
                lines.append(f"{key}: added `{item_id}`")
            for item_id in old.keys() - new.keys():
                lines.append(f"{key}: removed `{item_id}`")
            for item_id in new.keys() & old.keys():
                fields = sorted(
                    f
                    for f in new[item_id].keys() | old[item_id].keys()
                    if new[item_id].get(f) != old[item_id].get(f)
                )
                if fields:
                    lines.append(f"{key}: `{item_id}` changed ({', '.join(fields)})")
            if [i for i in old if i in new] != [i for i in new if i in old]:
                lines.append(f"{key}: order changed")
        elif before.get(key) != after.get(key):
            lines.append(f"`{key}` changed")
    return sorted(lines) or ["No changes."]


def integration_steps(case: Case, kind: str) -> list[str]:
    training = ROOT / "data/training/topics" / f"{case.id}.yaml"
    steps = [
        "Inspect this sheet and the YAML diff; resolve the catalogue slot and voice/avatar "
        "constraints (docs/NEW-STATION-PROCESS.md).",
    ]
    if training.exists():
        written_for = (yaml.safe_load(training.read_text()) or {}).get("case_version")
        steps.append(
            f"Update the topic training phrasings in `data/training/topics/{case.id}.yaml` "
            f"(written for version "
            f"{written_for}) for added, changed or removed facts and set `case_version: "
            f"{case.version}`. Until then this case's topics use the model route."
        )
    else:
        steps.append(
            f"Write and review topic training phrasings in `data/training/topics/{case.id}"
            ".yaml`. Until they exist, this case has no topic classifier."
        )
    steps += [
        "Write a few independently worded evaluation questions with expected fact IDs, kept "
        "separate from training phrasings, run the interpreter evaluation and record the "
        f"result with version {case.version}.",
        "Decide whether the student or reranker needs retraining; until then the status page "
        "reports this case as newer than the model's training set.",
        "Run the full checks, record the author review (status `author_reviewed`), then add "
        "the case to `data/cases/`.",
    ]
    if kind == "revision":
        steps.insert(1, "Update the version on evaluation files for this case after review.")
    return steps


def review_sheet(
    draft: StoredDraft, case: Case, case_data: dict, dropped: list[str], source_changed: bool
) -> str:
    before = plain(draft.source_text) if draft.source_text and draft.kind == "revision" else None
    source = draft.source
    lines = [
        f"# Review sheet: {case.title}",
        "",
        "Not clinically validated. Original fictional case. Status: author draft.",
        "",
        f"- Case ID: `{case.id}`, version {case.version} ({draft.kind})",
        f"- Source: `{source.case_id}` {source.version}" if source else "- Source: none (new case)",
        f"- Draft: `{draft.draft_id}`, revision {draft.revision}, author {draft.author}",
        f"- Exported: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "Checks passed: the runtime case schema. This is not an author review, clinical "
        "validation or integration for practice.",
    ]
    if source_changed:
        lines += [
            "",
            "**The active source case has changed since this draft was created.** "
            "Compare both before integrating.",
        ]
    lines += ["", "## Changes", "", *[f"- {line}" for line in changes(before, case_data)]]
    if dropped:
        lines += [
            "",
            "## Comments not kept",
            "",
            "These source comments were attached to removed or rewritten items:",
            "",
            *[f"- `{line}`" for line in dropped],
        ]
    if draft.objectives.strip():
        lines += ["", "## Intended learning objectives", "", draft.objectives.strip()]
    if draft.notes.strip():
        lines += ["", "## Author notes", "", draft.notes.strip()]
    found = prompts(case)
    if found:
        lines += ["", "## Review prompts", "", *[f"- {p.message} ({p.checked})" for p in found]]
    lines += [
        "",
        "## Before this case can be used for practice",
        "",
        *[f"{n}. {step}" for n, step in enumerate(integration_steps(case, draft.kind), 1)],
    ]
    return "\n".join(lines) + "\n"


def export(draft: StoredDraft, case: Case, cases_path: Path, out_root: Path) -> Export:
    data = clean(draft.case)
    source_text = draft.source_text if draft.kind == "revision" else None
    text, dropped = render(data, source_text)
    if Case.model_validate(plain(text)) != case:
        raise ValueError("Exported YAML does not reproduce the checked case")
    source_changed = False
    if draft.source:
        active = cases_path / f"{draft.source.case_id}.yaml"
        source_changed = (
            not active.exists()
            or hashlib.sha256(active.read_bytes()).hexdigest() != draft.source.sha256
        )
    sheet = review_sheet(draft, case, data, dropped, source_changed)
    folder = (
        out_root / "exports" / f"{case.id}-{case.version}-r{draft.revision}-{draft.draft_id[:8]}"
    )
    folder.mkdir(parents=True, exist_ok=True, mode=0o700)
    (folder / f"{case.id}.yaml").write_text(text)
    (folder / "REVIEW.md").write_text(sheet)
    return Export(
        case=case,
        file_name=f"{case.id}.yaml",
        case_yaml=text,
        review_markdown=sheet,
        dropped_comments=tuple(dropped),
        source_changed=source_changed,
        saved_to=str(folder),
    )
