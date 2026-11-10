# CascAid — CASC simulator proof of concept

A local proof of concept for practising CASC-style psychiatric interview stations with a
simulated patient, relative or colleague. It is intended for a poster or paper and asks
whether a fully local, privacy-preserving simulated patient, held to a structured hidden
case state, can run on consumer hardware with acceptable latency and fidelity to the case.

Cases are original fiction written to the March 2023 CASC blueprint. They are **not
clinically validated**, and automated feedback is not a CASC mark. This is educational
research software, not clinical decision support. See the [plan](docs/CASC-POC-PLAN.md).

This public repository starts from a single snapshot. Git tags named in the documents
(`paper-v1`, `realism-1`, `realism-2`, `cascade-1`, `cascade-2`, `pre-casc-archive`) refer to
the private development history and are not included here.

## Status

Phases 0–4 are complete apart from human ratings and real-voice recordings. Five original stations (history, collateral history, risk
assessment, addiction, explaining treatment to a relative) run end to end: reading time,
a typed or spoken 7-minute interview with a disclosure-gated role-player on the local model,
and automated feedback: which key facts were elicited and when, station tasks with quoted
evidence, and descriptive communication indicators on an annotated transcript. Every session is logged as JSONL in
`data/sessions/`; `npm run feedback -- --summary data/sessions/*.jsonl` recomputes
feedback from saved logs. Results and limitations:
[Phase 1](docs/CASC-POC-PLAN.md#phase-1-results),
[Phase 2](docs/CASC-POC-PLAN.md#phase-2-results),
[Phase 3](docs/CASC-POC-PLAN.md#phase-3-results),
[Phase 4](docs/CASC-POC-PLAN.md#phase-4-results) (human ratings and real recordings pending).

## Start the application

Step-by-step instructions for installing, starting, stopping and restarting everything
(model, speech and voice servers included) are in
[docs/GETTING-STARTED.md](docs/GETTING-STARTED.md).

Prerequisites: Node 22 or newer, npm and uv. From the repository root:

```sh
npm run dev
```

On first start this copies `.env.example` to an ignored `.env` and installs locked
dependencies. Open http://127.0.0.1:3105 for the station list and
http://127.0.0.1:8105/docs for the API. Ctrl-C or `npm run dev:stop` stops it.

`MODEL_BACKEND=fake` (the default) uses deterministic in-process models. For the local
model on Apple Silicon:

```sh
npm run models:install   # one-time pinned download (~3.1 GB), SHA-256 verified
npm run models:start     # leave running; Qwen3 4B on port 8180, Qwen3-Embedding 0.6B on 8181
```

Then set `MODEL_BACKEND=local` in `.env` and restart `npm run dev`. There is no hosted
fallback. (`QA_BACKEND`, the earlier name, is still accepted.)

By default (`INTERPRETER=cascade`) fast local classifiers trained on `data/training/`
interpret most trainee lines, and the Qwen interpreter handles the rest; this cut the median
turn from 4.9 s to 2.9 s in evaluation. `INTERPRETER=model` uses Qwen for every line.

### 3D character (experimental)

```sh
npm run avatars:install   # needs Blender 4.5.14; downloads pinned Rocketbox (MIT) characters and converts them
```

Then tick "Show the character" in a station. Each case has its own character and voice, and
its face follows the case's affect stage (`expression` in the case file). `/avatar-lab` shows
any installed character with each expression. See
`docs/QWEN-SPECIFICATION.md`, section 11.

### Character voice (optional)

```sh
npm run tts:install   # one-time: pinned HeadTTS (MIT) and Kokoro-82M (Apache-2.0), ~0.33 GB
npm run tts:start     # leave running; port 8183, loopback only
```

Set `TTS_BACKEND=local` in `.env` and restart the API. *Read replies aloud* then uses the
character's own voice (American for now), sentence by sentence as the reply is released, and
the 3D character's lips follow the voice's viseme timings. Synthesis never overlaps Qwen.
Without it, replies are read by an on-device browser voice.

### Speech input (optional)

```sh
npm run speech:install   # one-time: builds pinned whisper.cpp with Metal (~1 min), model ~0.5 GB
npm run speech:start     # leave running; Whisper small.en on port 8182 (add -- --model ggml-large-v3-turbo-q5_0.bin for the larger model)
```

Set `SPEECH_BACKEND=local` in `.env` and restart `npm run dev`. In a station, click
**Speak to …**, talk, and click again to stop. The recognised text appears in the box to
review or edit before sending (or tick *Send speech without reviewing*). Recording uses the
browser microphone; audio goes only to the local server and is never saved. Session logs
record the transcript, whether it was edited, and timings. *Read replies aloud* uses an
on-device system voice; network voices are never used. Typing always works. Tick *Hands-free conversation* to talk without clicking: speech
is detected in the page (Silero VAD, served by the app), sent when you pause, and speaking
over the character stops it (headphones recommended).

## Verify

```sh
npm test                  # API and web unit tests
npm run lint:api && npm run format:api:check
npm run typecheck:web && npm run lint:web
npm run contracts:check
npm run build:web
npm run test:e2e          # with npm run dev running; npx playwright install chromium once
npm run eval:interpreter -- --backend local --out artifacts/eval/interpreter.json
npm run eval:asr -- --interpret --out artifacts/eval/asr.json   # needs speech:start and models:start
npm run eval:indicators -- --out artifacts/eval/indicators.json
npm run eval:voice -- --out artifacts/eval/voice.json   # time to first audio; needs models, tts:start and the API
```

## Phase 4 evaluation

```sh
npm run eval:fidelity -- --judge qwen3-8b-q4-k-m --out artifacts/eval/fidelity-4b.json
npm run eval:fidelity -- --rejudge artifacts/eval/fidelity-4b.json --judge <other> --out …
npm run experiment:install -- qwen3-8b-q4-k-m && npm run experiment:start -- qwen3-8b-q4-k-m
npm run eval:fidelity -- --model qwen3-8b-q4-k-m --out artifacts/eval/fidelity-8b.json
npm run eval:interpreter -- --model qwen3-8b-q4-k-m
npm run eval:ratings -- artifacts/eval/fidelity-*.json      # blind CSV to rate by hand
npm run eval:agreement -- <sheet.csv> <key.json>            # judge vs human agreement
```

`eval:fidelity` runs the scripted interviews in `data/evaluation/scripts/` (complete,
partial and adversarial for every case) through the real pipeline, judges every reply,
and reports fidelity classes, adversarial probe pass rates, checklist accuracy against
what each script was designed to elicit, per-stage latency and model-server memory.

**Recording real voices (opt-in).** Set `RECORDINGS_ENABLED=true`, restart `npm run dev`
and open http://127.0.0.1:3105/record. Each speaker gives consent and a pseudonym, then
reads the 95 evaluation prompts; WAVs and a manifest are saved under `data/recordings/`
(ignored by git). Then run `npm run eval:asr -- --manifest data/recordings/<pseudonym>/manifest.yaml`.
Check whether recording colleagues needs consent paperwork at your institution.

## Repository layout

```text
apps/web/          Next.js station UI, generated API types, component and browser tests
services/api/      FastAPI, case schema, source registry, local model adapters, tests
data/cases/        Versioned YAML station cases (original fiction, CC BY 4.0)
config/            Source registry, model register, native runtime, hardware profile
scripts/           Dev server, model install/start/stop, contracts, hardware inventory
docs/              CASC POC plan, architecture, decision log, permission records
```

## Writing a case

The whole process for a new station, from draft to training, is in
[docs/NEW-STATION-PROCESS.md](docs/NEW-STATION-PROCESS.md).

Full guide: [docs/ADDING-A-STATION.md](docs/ADDING-A-STATION.md). To draft one with an LLM, use the prompts in [docs/LLM-STATION-PROMPT.md](docs/LLM-STATION-PROMPT.md). In short: add `data/cases/<id>.yaml` (see `elevated-mood-history.yaml`). The schema in
`services/api/src/psychiatry_api/cases.py` enforces the blueprint's skills, subdivisions,
specialties and timings. Facts are `volunteered`, `on_direct_question` or `after_rapport`;
mark checklist facts with `key: true`. The API never sends facts to the browser before the
debrief. Lessons from Phase 1:

- **Write each fact as a direct answer** to the questions in its `asked_about` labels.
  ("Yes, I'd planned it. I bought the tablets two days ago" — not just the purchase,
  which the model filled with "I didn't plan it".)
- **Keep `asked_about` labels distinctive** between facts. The first two labels form the
  interpreter's topic key; overlapping words (e.g. "tablets" in two facts) cause errors.
- Link each task to evidence where possible: `evidence_indicator` (summary,
  check_understanding, empathy, open_question) or `evidence_fact`; others are shown for
  self-review.
- Add labelled utterances to `data/evaluation/interpreter/` for new cases, then run
  `npm run eval:interpreter -- --backend local`.

## Project boundaries

- Fictional cases only; no real patient data, RCPsych station scripts or question banks.
- All inference runs on this machine; audio will not be retained by default.
- Every case and feedback screen states it is not clinically validated.
- Read `AGENTS.md` before implementation.

## Licence and copyright

Copyright © 2026 Steve J White. All rights not granted below are reserved.

- **Code** (everything not listed below) is licensed under the
  [GNU Affero General Public License v3.0 only](LICENSE) (`AGPL-3.0-only`). If you run a
  modified version as a network service, you must offer its users the source code.
- **Content**: station cases (`data/cases/`), the station catalogue (`data/catalogue/`),
  evaluation and training data (`data/evaluation/`, `data/training/`, `data/finetune/`)
  and documentation (`docs/`, `*.md`) are licensed under
  [Creative Commons Attribution 4.0 International](LICENSE-CONTENT) (`CC-BY-4.0`).

Other licences (for example a commercial licence without AGPL obligations) are available
from the copyright holder. See [NOTICE](NOTICE) for attribution and third-party components,
and [CONTRIBUTING.md](CONTRIBUTING.md) before opening a pull request.

CascAid is educational research software. It is not a medical device or clinical decision
support, and its cases and feedback are not clinically validated.
