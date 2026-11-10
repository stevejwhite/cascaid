# AGENTS.md — project instructions

## Mission
Build a local proof of concept of a CASC-style simulated psychiatric interview for a
poster or paper. Trainees interview a role-played patient, relative or colleague and
receive automated feedback. It is educational research software, not clinical decision
support, and it makes no claim of clinical validity. Plan: `docs/CASC-POC-PLAN.md`.
The earlier broad learning platform is archived at git tag `pre-casc-archive`.

## Non-negotiable rules
1. **The case is the source of truth.** Role-play may only reveal facts in the case file,
   subject to their disclosure rules. Never show the role-player model a fact it may not yet
   reveal; never let it invent clinically meaningful facts.
2. **Fiction only.** Cases are original and synthetic. No real patient data, and no RCPsych
   station scripts, question banks or eLearning content.
3. **Pinned blueprint.** Station structure follows the CASC blueprint version pinned in
   `config/sources.yaml`. Changing it requires a new registry entry and case versions.
4. **No silent source expansion.** Never ingest or persist an external source unless it is
   in `config/sources.yaml` with a permitted status.
5. **Local only.** Generation, speech recognition and speech synthesis run on this machine.
   No hosted fallback. Audio is not retained by default; transcripts stay local.
6. **Provider independence.** Access models through `psychiatry_api.models` adapters.
7. **Deterministic where possible.** Disclosure state, timing, checklist marking, IDs and
   scoring are code, not LLM judgement. Model-assisted judgements must be labelled as such
   and quote the transcript.
8. **Honest labelling.** Every case and feedback screen states it is not clinically
   validated. Communication indicators are descriptive, never presented as CASC marks.
9. **Measurable claims.** Every claim intended for the paper needs a reproducible script and
   ground truth that needs no clinical judgement (latency, WER, fidelity against the case,
   checklist accuracy on seeded transcripts).
10. **Tests are part of the feature.** New role-play, speech or marking behaviour needs unit
    tests and, where appropriate, an evaluation case.

## Development principles
- Python: type hints, Pydantic models, pytest, Ruff.
- TypeScript: strict mode, generated API types (`npm run contracts:generate`), component tests.
- Keep modules small; one function per workflow rather than mode flags.
- Version prompts under `prompts/`; record model, prompt and case versions with every turn.
- Commit in small, reviewable steps.
- Do not commit credentials, recordings, transcripts of real people or copyrighted dumps.
