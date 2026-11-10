# Architecture — CASC simulator POC

Scope and phases: [CASC-POC-PLAN.md](CASC-POC-PLAN.md). Decisions: [DECISIONS.md](DECISIONS.md).

## Principle

The case file is the source of truth; the language model only performs it. The role-player
is shown the persona and the facts its disclosure rules currently allow, so it cannot
reveal a fact it has not been given. Disclosure state, timing and checklist marking are
deterministic code. Everything runs locally on one Apple Silicon machine.

## Components

```text
Browser (Next.js, apps/web)
  │  /backend/* proxied to the API; never receives hidden case facts
  ▼
FastAPI (services/api)
  ├─ cases.py        case schema + loader (data/cases/*.yaml), blueprint validation
  ├─ sources.py      source registry policy (config/sources.yaml)
  ├─ health.py       readiness: registry, cases, local generation model
  ├─ models/         provider-neutral adapters; llama.cpp OpenAI-compatible client; fakes
  └─ (Phase 1+)      role-play engine, disclosure log, session JSONL, feedback
        │
        ▼
llama.cpp server (Metal, 127.0.0.1:8180)   pinned build + SHA-256-verified GGUF
whisper.cpp server (Metal, 127.0.0.1:8182)  pinned source build + SHA-256-verified model
```

No database: cases are versioned YAML, and sessions/transcripts will be JSONL files under
an ignored directory (ADR-011).

## Case model

A case records its CASC blueprint coordinates (skill, subdivision, specialty, communication
focus, pinned blueprint version), timing (7-minute station; 90 s or 4 min reading),
authorship (always `clinically_validated: false` in the POC), candidate instructions, a
persona, facts with disclosure rules and marking domains, and candidate tasks.
`CaseSummary` is the only case shape exposed over HTTP.

## Turn flow (Phase 1)

Code: `services/api/src/psychiatry_api/roleplay/`.

1. **Interpret** (`interpret.py`). One constrained JSON call (`casc-interpret-v1`) sees the
   utterance, the previous exchange and every fact's question labels, never fact content.
   It returns a short paraphrase (`focus`), up to three topic keys (or `none_of_these`)
   and a rapport flag. Topic keys are built from each fact's first labels, because bare
   fact IDs misled the 4B model. Failures fail closed: nothing is unlocked.
2. **Disclose** (`disclosure.py`, deterministic). Asked `on_direct_question` facts unlock;
   `after_rapport` facts unlock only if rapport has been shown, otherwise they are
   recorded as deferred and must be asked again. The result lists the facts this reply
   should use (`answering`).
3. **Respond** (`respond.py`). One generation call (`casc-roleplay-v1`, temperature 0.3,
   per-turn seed). The system prompt holds the persona and only currently known facts;
   a private note on the latest utterance names the facts to voice, or says to hesitate
   (deferred), deflect (unanswerable question) or respond naturally (empathy, greetings).
   The role-player only verbalises what the interpreter selected.
4. **Guard** (deterministic). Strips stage directions and name prefixes, trims replies cut
   off at the token limit, and replaces character breaks with the case deflection. It can
   remove or replace text, never add it.
5. **Log** (`sessions.py`). Each session is an append-only JSONL file in `data/sessions/`
   (ignored by git): a snapshot of the case with its SHA-256, then each turn's utterance,
   focus, asked/unlocked/answering/deferred facts, reply, seed, guard flags, per-call
   tokens and timings. State is rebuilt by replaying the log. The server enforces the
   reading phase, the 7-minute deadline (plus 15 s grace) and one model request at a time.

Fake mode swaps in a keyword interpreter and a template role-player that recites facts,
so the whole flow runs and is tested without a model.

## Speech input (Phase 2)

The browser records the microphone with an AudioWorklet, downsamples to 16 kHz mono and
encodes 16-bit PCM WAV in memory (`apps/web/lib/audio.ts`, `recorder.ts`). It posts the WAV
to `POST /api/sessions/{id}/transcriptions`, which validates the format and length (0.3–60 s),
forwards it to the loopback whisper.cpp server (`speech.py`, behind a `Recognizer` protocol
with a fake for tests) and returns the text. A `transcribed` event logs the text, the raw
recogniser output, the prompt, audio length and recognition time, never the audio. The
recognised text goes into the composer for review; the turn then carries its
`transcription_id`, and the log records `input: speech` and whether it was `edited`.
Transcription shares the single model slot with generation, so timings are not confounded.
The recogniser prompt is only "A psychiatry interview with {name}", to fix the
character's spelling without biasing recognition towards undisclosed case topics.

Replies can be read aloud with the browser's speech synthesis, restricted to on-device
voices (`localService`). This is a basic system voice; neural TTS is further work.

## Feedback (Phase 3)

`feedback/report.py` computes feedback deterministically from a session log, so the same
log always yields the same feedback (`GET /api/sessions/{id}/debrief`, `npm run feedback`).

- **Information gathering:** each fact is elicited (with question number and time into the
  interview), offered unprompted, held back (asked before rapport) or missed. The score
  counts key facts the candidate had to ask for; volunteered facts are excluded.
- **Communication indicators** (`feedback/indicators.py`, `indicators-v1`): rules tag each
  utterance's question type (open, closed, none), stacked questions, summaries, checks of
  understanding and listed technical terms; empathy reuses the interpreter's rapport flag
  (model-assisted, labelled as such). Also the candidate's share of words and spoken/edited
  turns. All are descriptive and shown with the utterance they came from.
- **Tasks:** a case task links to an indicator or a fact as evidence; tasks without a link
  are shown for self-review rather than guessed.

## Provenance

The model register pins the generation model revision, artifact checksum and runtime
build; `models:start` verifies them and the API re-checks served properties. The CASC
blueprint is a registry item pinned by version and checksum; only its station structure
is encoded, and no full text is indexed.
