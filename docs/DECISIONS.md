# Architecture Decision Log

## ADR-001 — Education first
**Decision:** MVP is an educational tool using synthetic cases and no real patient data.

**Reason:** Delivers useful functionality while avoiding premature clinical decision-support and patient-data complexity.

## ADR-002 — Evidence-first RAG
**Decision:** Use retrieval over approved/versioned evidence rather than fine-tuning a model to contain the core medical knowledge.

**Reason:** Improves traceability, updateability and licence control.

## ADR-003 — Provider-independent LLM layer
**Decision:** Model access is abstracted behind an internal adapter.

**Reason:** Models will change; the evidence/data/evaluation assets should outlive any one provider.

## ADR-004 — Hybrid retrieval
**Decision:** Combine lexical and vector retrieval.

**Reason:** Psychiatry education contains exact identifiers, legal sections, drug names and diagnostic terminology where lexical matching remains important.

## ADR-005 — Modular monolith for MVP
**Decision:** Keep clear logical modules but avoid premature distributed microservices.

**Reason:** Simpler local development in VS Code/Codex and faster iteration.

## ADR-006 — Original curriculum ontology
**Decision:** Create our own topic/learning ontology and map to third-party curriculum references only where permission allows.

**Reason:** Avoid building the core data model around copyrighted curriculum wording.

## ADR-007 — Local-first open-weight models
**Decision:** Run generation and embeddings locally by default through provider-independent
adapters. Hosted model access, if added, must be explicitly configured and disabled by default;
the application must never silently fail over to it.

**Reason:** Local-first inference gives the project control over privacy, deployment and model
replacement. It also permits offline development and evaluation. Model eligibility and release
are governed by licence review and task-specific evaluation rather than by a permanent choice
of model vendor.

**Delivery plan:** See `docs/PROTOTYPE-PLAN.md` and `docs/LOCAL-LLM-PLAN.md`.

## ADR-008 — current Mac environment and application sequence

**Decision (2026-09-26):** Use the Apple M4/16 GiB host as the active developer profile,
uv-managed Python 3.12 for FastAPI, strict TypeScript for Next.js, an ARM64 PostgreSQL/
pgvector container and native Metal inference. Keep Windows model benchmarks historical.

**Reason:** This matches the available environment and avoids CPU-only assumptions or a
container boundary around GPU inference. Existing Node contracts remain reference fixtures
for the Python implementation, not a requirement to add another application service.

## ADR-009 — staged source activation

**Decision (2026-09-26):** Start with a narrow approved GOV.UK/legislation corpus after the
fixture vertical slice. Extend to conditional sources independently. Keep permission-gated
providers visible in the source catalogue without ingesting them. Record per-item versions
and licences and enforce the registry before embedding and when retrieving.

**Reason:** A working prototype must have honest source coverage and must not depend on
permissions that have not been granted. Public availability and account access are not
equivalent to permission for the intended AI/product use.

## ADR-010 — narrow to a CASC simulated-interview proof of concept

**Decision (2026-10-07):** Replace the broad MRCPsych learning platform with a local CASC
station simulator for a poster/paper. Cases hold a hidden structured state; the role-player
model sees only the persona and currently disclosable facts. The previous platform is
preserved at git tag `pre-casc-archive`. Plan: `docs/CASC-POC-PLAN.md`.

**Reason:** The broad scope outran its evidence base (99.6% Wikipedia passages), human
review and evaluation. CASC tests communication skills, so its core assets are authored
cases and checkable feedback rather than a large clinical corpus. No clinician time is
available, so evaluation measures properties checkable against the case file.

## ADR-011 — no database for the POC

**Decision (2026-10-07):** Remove PostgreSQL/pgvector. Cases are versioned YAML in
`data/cases/`; sessions and transcripts will be JSONL files.

**Reason:** Nothing in CASC scope uses retrieval. Files are easier to analyse, publish and
reproduce, and removing Docker simplifies setup for other researchers.
