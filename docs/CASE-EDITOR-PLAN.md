# Visual case authoring for CascAid

Status: proposed, 9 November 2026; revised 10 November 2026 after review against the code
(author access, integration and version linkage, comment preservation, estimates).
Phases 0, 1, 2 and V implemented on 10 November 2026 for local use; see the implementation
record at the end. Phases 1b (YAML import), R (remote author instance) and 3 are not built.

## Purpose and first release

Let a clinician create, duplicate and edit an original fictional case without writing
YAML. Make the relationship between each fact, its disclosure conditions and feedback
visible. Preserve the existing case schema and disclosure engine as the source of truth.

Start with a local, single-author editor that saves drafts, checks them and exports a
case for integration through the existing station process. A usable first release does
not require AI drafting, model training, a graphical programming canvas or live role-play.

Initial users are the two doctors planning small clinical education projects. Their
first authoring tasks should use copies of `alcohol-history`, `amputation-refusal-capacity`
and `memory-collateral-history`, rather than require new case collections. They do not
work at the host Mac and should not need to install the repository, so how they reach the
editor is decided in phase 0 (see **Author access**).

Success: each doctor can change a case fact, change its disclosure condition, understand
the resulting behaviour, save and reopen the draft, and export a valid case without
editing YAML. This is a usability target, not a claim of clinical or educational validity.

Exporting a valid case is not the same as making it available for practice. Integration
needs new or revised interpreter training phrasings and a recorded evaluation (see
**From export to practice**). Set that expectation with the doctors from the start.

## What exists already

- `services/api/src/psychiatry_api/cases.py` defines `Case`, facts, tasks, character
  questions, affect stages, permitted blueprint values and timing constraints.
- `roleplay/disclosure.py` implements disclosure state, vague/full answers, rapport
  conditions and affect transitions. Reuse it; do not reproduce its rules in JavaScript.
- `roleplay/respond.py` builds the role-player's permitted context and guards replies.
- `roleplay/sessions.py` snapshots cases and records the interview. `feedback/report.py`
  derives feedback from disclosure events, which does not itself prove the generated
  reply actually expressed the fact correctly.
- The web app has a station runner and generated API contracts, but no authoring editor
  or full-case author API. Learner-facing responses intentionally exclude hidden facts.
- Shipped-case tests also enforce catalogue membership and voice/avatar constraints.
  Saving a schema-valid draft alone is therefore insufficient to add a teaching station.
- Each case's topic classifier is trained from authored phrasings in
  `data/training/topics/<case>.yaml`, which record `case_id` and `case_version`.
  `test_training_files_match_their_cases` rejects a version or fact mismatch. A case
  with no phrasings has no topic classifier and falls back to the slower model route.
  The fine-tuned student and reranker were trained on the existing cases.
- Sessions snapshot the full case, its file hash and interpreter/role-player prompt
  versions, so past sessions remain interpretable after a case changes.

References: [authoring guide](ADDING-A-STATION.md), [station process](NEW-STATION-PROCESS.md),
[project plan](CASC-POC-PLAN.md), [architecture](ARCHITECTURE.md).

## Screen and author workflow

Use a guided form with a persistent preview. Avoid an editable node graph initially:
the current engine supports a small set of conditions, not arbitrary dialogue branches.

```text
Case editor       Memory collateral history       Draft saved       Export case
Not clinically validated. Original fictional cases only.

Sections                   Editor                              Preview
1. Station                 Fact: Baseline independence         Candidate view
2. Character               Patient/relative's own words        or Disclosure view
3. Facts and disclosure    Questions about this fact
4. Feedback tasks          When it may be shared               Available / Held back
5. Check and export        [When asked v]                      / Partial / Released
                           [x] Include in information checklist

                           Optional initial vague answer       Why this state applies
                           Save changes                        Check messages
```

On narrower screens, the preview is a separate tab. All controls work with keyboard
navigation. Facts have move-up/down buttons; dragging is optional, never required.
Use text labels as well as colour for states and errors.

### 1. Choose a starting point

- **Create a case:** a blank draft with guided required fields and permitted defaults.
- **Copy an existing case:** select from a local author-only list; open a separate draft.
- **Continue a draft:** show title, last saved time, source case and check status.
- Support a local YAML import for existing work; accept data only, not executable tags,
  file paths or remote URLs. Display errors without destroying the imported text.

Distinguish “new case” from “revision of an existing case”. A new case gets a new stable
slug and starts at `0.1.0`; a revision keeps its case ID and proposes a version increment
for export. Temporary draft revisions are separate from released case versions.
Changing the title must not silently change the case ID.

### 2. Station details

Fields: title, candidate instructions, skill, subdivision, specialty, communication
focus, reading time and author name. Show the pinned blueprint version as read-only.
Filter subdivisions by skill. Interview time remains seven minutes; reading choices
remain 90 or 240 seconds, consistent with the current schema.

Provide brief guidance on writing a bounded task. Keep working notes and intended
learning objectives in draft metadata; they are not additional facts for the role-player.
Show objectives on the review sheet. Do not add unrecognised fields to exported `Case`.

### 3. Character

Fields: patient/relative/carer/colleague, name, age, background, speech style, initial
affect, opening statement and the response to questions outside the case.
Explain that facts the learner must elicit belong on fact cards, not in background or
opening text that is available from the start.

Use existing voice/avatar choices under an optional presentation section. Preserve
existing values. Drafts can be prepared before choosing presentation assets; final
integration must meet the shipped-case catalogue and presentation checks.

### 4. Fact cards: the main authoring surface

Each card contains:

| Clinician-facing field | Existing case field / behaviour |
|---|---|
| What the character says | `content`: explicit answer in the character's own words |
| Questions about this fact | `asked_about`: topic labels/example phrasings for interpretation |
| Feedback area | `domain` |
| Include in information checklist | `key`; volunteered facts are excluded from the elicitation total |
| Can be volunteered | `disclosure: volunteered` |
| Share when asked | `disclosure: on_direct_question` |
| Share when asked after rapport | `disclosure: after_rapport` |
| Rapport condition | Existing `rapport_needed` values 1 or 2; explain as simulation settings |
| Initial vague answer | Optional `vague`; unavailable for volunteered facts |

Explain that question labels support interpretation; they are not an exhaustive list
of exact phrases a learner must use. Encourage one independently askable topic per fact.
Do not silently reorder labels: their order currently matters to interpreter topic keys.

Create deterministic, collision-checked IDs from the initial label, with numeric suffixes
where needed; retain them through text edits. IDs are an advanced detail. Duplicating a
card creates a new ID. Deleting a referenced fact must show its linked tasks/questions
and require their repair or explicit removal within the editor.

Optional sections expose existing affect stages, alternative deflections and character
questions. Character questions support only the current time or fact triggers. Affect
stages support only current rapport/confrontation conditions. Do not imply arbitrary
dependencies or a clinically validated model of trust, cognition or emotion.

### 5. Feedback tasks

Write the task and choose one evidence source: a fact, an existing communication
indicator, or self-review. The controls mirror the schema's mutually exclusive links.
Keep subjective judgements such as overall empathy or professionalism as self-review
unless an existing supported indicator is explicitly chosen and labelled descriptively.
Never offer a CASC pass mark or a clinical-validation switch.

## Preview: two distinct views

**Candidate view:** station instructions and opening presentation only. Render from a
candidate-safe projection, not the full draft. Hiding a panel in the browser is not an
access-control boundary: the author is authorised to see all facts, ordinary learners
must still receive only their existing restricted API responses.

**Disclosure view, first release:** show cards grouped as available from the start,
requires a question, and requires a question plus rapport. A selected-turn simulator
lets the author choose which fact was asked about, the existing empathy level and
whether the line was confrontational. Apply the actual Python disclosure functions and
display partial/released/held-back states, current affect and a plain-language reason.
Allow reset and a sequence of turns so decay, follow-up and confrontation are represented.

Label this “Rule preview — question recognition and generated replies are not tested”.
The control inputs are manual stand-ins for the interpreter; never present this as a
successful natural-language interview. Include the exact permitted fact text in an
author-only inspector, including only vague text before a follow-up unlocks the full fact.

**Live conversation, later phase:** test a frozen draft snapshot with local models.
Show the interpreted topics, disclosure events and actual reply separately. This lets an
author distinguish an interpretation error from a disclosure or generation problem.
An edit requires a new preview session; it cannot change a running encounter.

## Drafts, saving and export

- Keep active cases in `data/cases/` unchanged during editing. Store drafts in a separate
  ignored `data/authoring/` directory, never scanned by the learner case loader.
- Use a draft envelope with server-assigned draft ID, revision number, source ID/version/
  content hash, original YAML, editable case fields and author notes. Allow incomplete
  drafts to save; full `Case` validation is required for rule preview and case export.
- Provide explicit Save plus a dirty/saving/saved/error indicator and navigation warning.
  Autosave and a revision-history interface can follow if needed. Reject stale saves
  from another tab with a clear conflict message; do not silently overwrite.
- Write atomically within the managed directory; accept IDs rather than filesystem paths.
- Preserve all supported fields and their ordering when editing an existing case.
- Comments: all 61 shipped cases have comments, mostly a two-line provenance header.
  Guarantee the header and comments on fields the author did not edit. Comments attached
  to deleted or reordered items cannot be preserved reliably. List every comment that
  export would drop and require acknowledgement; never drop one silently. Encourage
  clinical reasoning in structured author notes in the draft envelope rather than YAML
  comments. Round-tripping needs a comment-aware YAML library (for example
  `ruamel.yaml`, a new dependency); confirm its behaviour on fixtures in phase 0.
  Retain the source text for recovery.
- Export valid YAML plus a human-readable change/review sheet. Preserve the original file;
  exporting a revision does not overwrite the active station. Downloaded draft bundles can
  preserve working notes separately from the runtime case file.
- Keep `clinically_validated: false`. Export always writes `authorship.status:
  author_draft`; only the integration workflow sets `author_reviewed`, after a recorded
  author review. A recorded author review is not clinical validation.
- Distinguish “Saved”, “Schema checks passed”, “Author reviewed” and “Integrated for practice”.
  Never use a single green badge implying all four.

For the first release, integration remains the existing reviewed development workflow
described in **From export to practice**. Retain the source hash to detect edits to an
active case since the draft was created. Do not automatically allocate mock-exam slots,
change the pinned blueprint, retrain models or start a teaching session from an
unintegrated draft.

## From export to practice

This is the developer's work after an export, not the editor's. Estimate it separately
for each case; for a revised or new case it is usually larger than the editing itself.

1. Inspect the exported diff and review sheet; resolve the catalogue slot and check
   voice/avatar constraints.
2. Bump the case version. A new case starts at `0.1.0`.
3. Topic training phrasings. Revised case: update `data/training/topics/<case>.yaml` for
   added, changed or removed facts and set its `case_version`. New case: write a new file.
   Drafting may use local adapters only; every file is reviewed before `status: reviewed`.
   Until reviewed phrasings exist, the case is not integrated.
4. Evaluation. Write a few independently worded questions with expected fact IDs, kept
   separate from training phrasings (the near-copy test applies). Run the interpreter
   evaluation for the case and record the result with the case version.
5. Decide whether the student or reranker needs retraining. Until then, record that the
   case runs with models trained on an earlier case set, and label the route.
6. Run the full checks, set `author_reviewed` after the recorded review, then add the
   case to `data/cases/`.

**Version linkage.** Today a case version is linked to its sessions (full snapshot and
file hash) and to its training phrasings (by a test only). It is not linked to the
student/reranker or to evaluation sets. Add, as part of integration support:

- A runtime check: the classifier trainer skips, and logs, a case whose training file's
  `case_version` differs from the loaded case. The case then uses the model route rather
  than a stale classifier. Add a unit test.
- A case-set manifest recorded with each student/reranker training run (case IDs,
  versions and file hashes), stored beside the model's registry entry. Readiness or the
  status page reports cases newer than the model's manifest.
- `case_id` and `case_version` on evaluation items, with a test like the training one.

These are small code changes in the interpreter and training tooling, independent of the
editor. Implement them before the first doctor-authored case is integrated.

## Checks and scope boundaries

**Blocking structural errors:** existing schema violations, missing required fields,
duplicate IDs, broken task/question references, invalid disclosure combinations,
unsupported blueprint values and invalid versions. Show errors at the relevant control
with a linked summary. Reuse `Case` validation on the server.

**Author review prompts:** consistency of ages/dates/quantities; explicit relevant
negatives; distinct question labels; sensitive facts accidentally placed in the opening;
character questions that could reveal withheld information; and suitable responses to
reasonable questions outside the case. These require review, not an automated “clinically
safe” verdict. Simple text checks may flag possible issues but must say what they checked.

For each pilot case, prepare a few independently worded questions and expected fact IDs
before tuning labels. Keep development checks separate from held-out evaluation material.
Manual rule previews are demonstrations, not evidence of interpreter accuracy.

All cases remain original fiction. No real patient upload, web ingestion, station-bank
import or automatic source expansion. No hosted AI authoring or evaluation. The initial
editor uses no generation model; any future drafting assistance must use the project's
local adapters and existing source permissions.

## Implementation boundaries

Reuse the existing Next.js and FastAPI applications. Proposed modules:

- `services/api/src/psychiatry_api/authoring/`: draft store, validation, export and rule
  preview, with separate functions/endpoints for each workflow.
- `apps/web/app/authoring/`: local author entry point and editor pages.
- `apps/web/components/case-editor/`: station, character, facts, tasks and preview panels.
- `apps/web/lib/authoring.ts`: client calls using generated API types.

Expose author-only draft and full-case contracts under `/api/authoring`, with distinct
create, load, save, validate, rule-preview and export operations. Publish schema choices
from Python rather than maintaining a divergent TypeScript list. Regenerate contracts
with `npm run contracts:generate`. A relaxed draft contract must still reject unsafe
input; it is not a replacement runtime `Case` schema.

The full-case API is privileged. It is off by default and the authoring router is not
mounted at all in the `production-local` and `production-online` profiles. Hiding it is
not enough: the owner's verified Access sign-in would otherwise reach it through the
tunnel. No full cases in public static assets, prefetched learner pages or public API
contracts/responses. Check direct API access in tests, including against the
`production-online` app.

### Author access

Decide in phase 0. Phases 0–2 need no models, so an author instance is light.

- **Local only (developer use):** an explicit `AUTHORING_ENABLED` setting on a loopback
  development instance, with Origin checks on mutations. A separate per-author capability
  adds little on a loopback-only instance; the threat is a web page posting to localhost,
  which the Origin check addresses.
- **Remote, for the two doctors (recommended):** a separate author instance on the host
  Mac, without models or learner sessions, published on its own hostname (for example
  `author.<your-domain>`) through the existing Cloudflare tunnel. It has its own Access
  application allowing only the doctors' and owner's emails. Reuse the stage 2
  verification boundary with that application's audience, plus an author allowlist.
  Drafts are stored per author. This is a new deployment profile and needs its own
  tests; it does not change the learner pilot. It can run alongside production because
  it loads no models, but use distinct ports and data directories.

Remote collaborative editing of the same draft remains out of scope; stale-save
conflicts are rejected.

Before implementing, reread the current web `AGENTS.md` and installed Next.js guidance.
Build on the stage 2 access boundary (`psychiatry_api.access`, the `production-online`
profile and the `/backend/api/*` proxy) rather than adding a second mechanism.

## Small delivery phases and effort

Estimates are hands-on developer days, assuming the existing local app works. They are
planning ranges, not measured delivery times; clinician review time is additional.

| Phase | Deliverable | Effort | Completion criterion |
|---|---|---|---|
| 0 | Confirm contracts, comment handling and screen sketch with two existing cases; decide author access | 1–1.5 days | Header and unedited comments survive a round trip; dropped comments are listed; access option chosen |
| 1 | Forms, fact cards, copy/create, draft save/reopen, checks and export | 4–6 days | Each doctor can revise and export a valid case without YAML editing |
| 1b | YAML import and stale-save conflict detection | 1–2 days | Imported text is never destroyed; a stale save is rejected with a clear message |
| 2 | Visual disclosure groups and deterministic multi-turn rule preview | 1–2 days | Actual disclosure code explains available, held-back, partial and released facts |
| R | Remote author instance (if chosen): profile, Access application, author allowlist, per-author drafts | 1.5–2.5 days | Doctors sign in remotely; learners and unlisted emails are refused; no learner data is visible |
| V | Version linkage: stale-training runtime check, model case-set manifest, versioned evaluation items | 1–1.5 days | A mismatched case uses the model route and is reported; tests pass |
| 3, optional | Local live draft interviews with interpreter/disclosure/reply inspector | 2–4 days | Frozen draft sessions run without stale case-specific classifiers or learner exposure |
| Later, only if justified | Direct integration, collaboration, visual relationship map or local AI assistance | Separate estimate | A demonstrated author need |

**Recommended initial commitment: phases 0, 1, 2 and V, approximately 7–11 developer
days, plus R (1.5–2.5 days) if the doctors use it remotely.** Phase 1b can follow the
walkthroughs. Stop after two short clinician walkthroughs (30–45 minutes each), fix major
obstacles and use the editor for the small projects. Do not make either doctor's project
depend on phase 3. Integration of each exported case is estimated separately.

Phase 3 should initially use the existing general local model interpreter, explicitly
bypassing classifiers trained for an older case version. Label that preview route and
record it; it is not evidence of the final cascade's performance. Reuse session/disclosure/
response functions with a separate author-only session store and route set. Keep test
logs local and separate from study sessions; record draft revision, case hash, model and
prompt versions. Honour the shared generation lock. No speech or avatar work is needed
for this first live preview.

## Required verification for implementation

- Python: draft persistence, incomplete-draft recovery, conflict detection, safe import,
  schema errors, lossless preservation, stable IDs and reference integrity.
- Disclosure: compare preview sequences directly with production `apply`/`known`, including
  early sensitive questions, rapport decay, vague then full answers, confrontation and reset.
- Boundary: author APIs absent when disabled and in both production profiles (tested
  against the `production-online` app with a valid owner assertion); unauthorised
  reads/writes rejected; full case facts absent from ordinary learner endpoints; drafts
  excluded from station lists. Remote author instance: unlisted emails and learner-app
  assertions rejected; one author cannot read another's drafts.
- Version linkage: a training file with a stale `case_version` is skipped at runtime and
  reported; model manifests list case versions; evaluation items carry case versions.
- Components: create/copy/edit/save/reopen/export, accessible controls, visible save failures,
  linked validation errors, deleting referenced facts and preservation of advanced fields.
- Browser flow: edit a copy of the alcohol case, exercise its rule preview and export it;
  validate export with the runtime schema and confirm the original case is unchanged.
- When phase 3 is implemented: snapshot isolation, changed-case classifier bypass, model
  failure handling, local-only adapters and author/learner session separation.
- Run relevant pytest/component/browser tests, Ruff, TypeScript checks, generated-contract
  checks and the web build. The documentation-only planning change needs no runtime tests.

## Initial acceptance exercise

1. Doctor opens a copy of an existing case and edits one answer.
2. Doctor adds a fact and selects when it can be shared.
3. Doctor links a feedback task and sees a useful error if its fact is removed.
4. Doctor previews an early question, a rapport-building turn and a follow-up, and can
   explain why the fact remains withheld or becomes available.
5. Doctor saves, closes and reopens the draft with no lost fields or comments.
6. Export passes schema checks, lists any comments it would drop, and shows its changes
   and the outstanding integration steps (training phrasings, evaluation, model status).
7. Learner station content and active files remain unchanged throughout.

Record task completion, time, assistance required and confusing controls. Use these
observations to decide the next editor increment; do not present them as clinical validation.

## Implementation record (10 November 2026)

Built for the **local-only** access option: `AUTHORING_ENABLED=true` on a development
instance, refused in both production profiles. The remote author instance (phase R) is
not built; the two doctors cannot use the editor until it is, or until they use the host
Mac.

- **Server** (`psychiatry_api.authoring`): draft store with server-assigned IDs, atomic
  writes and stale-save rejection (phase 1b's conflict detection was cheap enough to
  include); relaxed draft contract limited to case fields and 256 KiB; checks using the
  runtime `Case` schema plus revision-version and ID-collision rules; review prompts that
  state what they checked; rule preview over the production `apply`/`known` functions;
  export to `data/authoring/exports/` with a review sheet listing changes, comments not
  kept, review prompts and the integration steps. Routes require the editor's own host
  (also via `x-forwarded-host`) and, for changes, its own Origin.
- **Comments:** merged with `ruamel.yaml`. All 61 shipped cases round-trip with every
  comment, and 48 are byte-identical; the other 13 only have plain multi-line strings
  joined onto one line. A comment is reported as not kept if it disappears or ends up
  beside a different item (for example above the next fact after a deletion).
- **Web** (`/authoring`, `/authoring/<draft>`): create, copy or revise; station,
  character, fact cards (move, duplicate, delete with link repair), tasks, optional
  behaviour (deflections, affect stages, character questions), author notes; explicit
  save with status and a leave-page warning; linked error summary; candidate view and
  rule preview. On narrow screens the preview stacks below the form rather than using a
  separate tab.
- **Version linkage (phase V):** stale topic training is skipped and logged; fine-tune
  export writes a case manifest and the status page reports cases newer than the pinned
  student's or reranker's manifest (`config/model-cases/`). No manifest exists yet for the
  current student, so the status page says its case set is not recorded. Interpreter and
  script evaluation files now carry `case_version`, stamped at each case's current version
  on this date (earlier history is not reconstructed) and enforced by a test.
- **Not built:** YAML import (1b), the remote author instance (R), live draft interviews
  (3), autosave and revision history. No clinician walkthrough has taken place.
- **Verification:** API 375 passed (26 authoring tests, including a randomised comparison
  of the preview with `apply`/`known` on every case, and a test that a verified owner
  assertion through the online profile finds no authoring routes), web 73 passed, browser
  tests 7 passed with the editor enabled (including the alcohol revision flow) and the
  editor test skipped when disabled. Ruff, TypeScript, ESLint, contract check and the
  production web build passed.

