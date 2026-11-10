# Qwen model specification

Status: sections 1–10 describe the Qwen3-4B configuration at git tag `realism-2`
(2026-10-08), with measurements from Realism Phase 2 gate run 3 unless stated. Since tag
`cascade-1` (2026-10-13) the default interpreter is the classifier cascade (section 11;
current version `cascade-2`),
which calls the same Qwen topic and tone prompts only for lines the classifiers are not
confident about. Not clinically validated; the model is not
release-approved (see [Licence and approval](#licence-and-approval)).

This document states what the project needs from its local language model, how each
capability is used, and what must be re-checked before the model or its runtime changes.

## 1. Role of the model

One local model does four jobs in every simulated interview turn and one job during
evaluation. It never decides what the character may reveal: disclosure state, marking,
timing and IDs are code ([AGENTS.md](../AGENTS.md), rule 7).

| Job | Prompt | Output | Sees hidden facts? |
|---|---|---|---|
| Topic interpretation: which case topics the trainee asked about (for lines the classifiers are not confident about; section 11) | `casc-interpret-v1` | JSON (schema-constrained) | No: topic labels only |
| Tone rating: empathy, confrontation, whether a character question was answered (likewise) | `casc-tone-v1` | JSON (schema-constrained) | No: the trainee's line only |
| Role-play: the character's reply | `casc-roleplay-v1` | Free text, 1 to 3 sentences | Only facts already unlocked (or their vague versions) |
| Baseline condition (evaluation only): whole-case role-play | `casc-roleplay-fullcase-v1` | Free text | Yes, by design of the comparison |
| Fidelity judge (evaluation only) | `fidelity-judge-v2` | JSON (schema-constrained) | Known facts for the turn |

The judge defaults to the evaluation-only 8B model (section 2) and was found unreliable;
human ratings are the primary fidelity measure.

## 2. Model and runtime identity

All values are pinned and checked at start-up and before each turn.

| Item | Value | Source |
|---|---|---|
| Model | Qwen3-4B, GGUF, `Q4_K_M` quantisation | `config/model-register.json` |
| Upstream | `Qwen/Qwen3-4B-GGUF` at revision `bc640142c66e1fdd12af0bd68f40445458f3869b` | same |
| File | `Qwen3-4B-Q4_K_M.gguf`, 2,497,280,256 bytes, SHA-256 `7485fe6f…5fdf5` | same |
| Alias sent as `model` | `Qwen/Qwen3-4B-GGUF:Q4_K_M` | `services/api/src/psychiatry_api/config.py` |
| Runtime | llama.cpp `llama-server` build b11149, commit `d2e54583c`, macOS arm64 release archive (checksum pinned) | `config/native-runtime.json` |
| Host | Apple M4, 10-core GPU, 16 GiB unified memory, Metal | `config/deployment-profiles.json` |
| Port | 127.0.0.1:8180 (loopback only) | `config/native-runtime.json` |
| Evaluation-only comparison model | Qwen3-8B `Q4_K_M`, revision `7c41481f…d974`, port 8183; never used by the application | `config/experiment-models.json` |

`npm run models:start` verifies the runtime archive, the binary's build identity and the
model file's checksum before starting the server. Before each turn the API reads the
server's `/props` and refuses to run (HTTP 503) unless the model path, build, alias, slot
count and per-slot context match the pinned values (`models/selection.py`,
`verify_service`).

### Server flags

| Flag | Value | Why |
|---|---|---|
| `--ctx-size` / `--parallel` | 4096 / 1 | One slot of 4,096 tokens: the tested context limit |
| `--gpu-layers`, `--device` | 99, `MTL0` | Whole model on the Metal GPU |
| `--flash-attn` | on | Memory and speed on Metal |
| `--batch-size` / `--ubatch-size` | 512 / 128 | Prompt processing batches |
| `--threads` | 4 | CPU threads for non-offloaded work |
| `--jinja` | on | Use the model's own chat template |
| `--reasoning off`, `--reasoning-budget 0` | off | Qwen3 "thinking" is disabled: no hidden reasoning tokens, lower latency |
| `--no-context-shift` | on | An over-long request fails instead of silently dropping context |
| `--offline`, `--no-ui`, `--metrics` | on | No network access, no web UI, local metrics |
| `--cache-ram` | 1024 MiB (from `cascade-2`; `cache_ram_mib` in `config/native-runtime.json`) | Caps the host-memory prompt cache, which otherwise grew the server's footprint to 9 GB |
| `--cors-origins` | `http://127.0.0.1:3105` only | Only the local web app may call it from a browser |

## 3. Interface

The API talks to the server through the provider-neutral adapter in
`services/api/src/psychiatry_api/models/` (`LocalLanguageModel`). No other code calls the
model directly, and there is no hosted fallback (`config/model-policy.json`).

Endpoints used:

| Endpoint | Use |
|---|---|
| `POST /v1/chat/completions` | Every generation, always with `stream: true` and `stream_options.include_usage: true` |
| `GET /health` | Readiness |
| `GET /props` | Identity and configuration check |

Request fields sent: `model`, `messages` (roles `system`, `user`, `assistant`),
`temperature`, `max_tokens`, `seed` (when set), `stream`, `stream_options`, and for
structured calls `response_format` = `{type: "json_schema", json_schema: {name, schema,
strict: true}}`.

## 4. Required capabilities

Each requirement is something the project depends on; a replacement model or runtime must
meet all of them.

| ID | Capability | How it is used | Verified by |
|---|---|---|---|
| Q1 | Chat completion with system, user and assistant messages | Every call; the role-play call replays the interview as alternating user and assistant turns | Unit tests; every evaluation run |
| Q2 | Server-sent-event streaming with a final usage block and `finish_reason` | Timing (first token), token counts, truncation detection. A stream without `[DONE]` or a finish reason is an error | `test_streaming.py`; adapter tests |
| Q3 | JSON-schema-constrained decoding (`strict`) | Topic, tone and judge calls. Output is also validated locally with `jsonschema`; invalid output raises `invalid_structured_output` | Interpreter and rapport evaluations |
| Q4 | Deterministic decoding at temperature 0 with a fixed seed | Topic and tone calls (`temperature 0`, `seed 0`), so the same input gives the same interpretation | Repeated runs give identical selections |
| Q5 | Seeded sampling | Role-play at temperature 0.3 with a per-turn seed (SHA-256 of session ID and turn index), so a session can be replayed | Session logs record the seed |
| Q6 | 4,096-token context per request | Prompts are kept under an estimated 3,156 tokens (80% of context, minus the 120-token reply allowance; estimate = characters / 4); the oldest turns are dropped first and the turn is flagged `history_trimmed` | `respond.py` (`PROMPT_BUDGET`) |
| Q7 | Output-length cap | 120 tokens for role-play, topic and tone; 400 for the judge. A reply cut off by the cap has its unfinished sentence dropped (flag `truncated`) | Guard tests |
| Q8 | Following short English instructions in character | Role-play rules: first person, 1 to 3 sentences, no stage directions, no added facts, no advice, never say it is an AI | Fidelity gates, probes, human ratings |
| Q9 | Copying words verbatim from the input | The tone call must quote the empathic or challenging words; code rejects quotes not found in the trainee's line | Rapport label set |
| Q10 | Disabled reasoning mode | Thinking tokens would add latency and could leak into replies | Server flags; `/props` |
| Q11 | Local Metal inference within the memory budget | Model, speech recogniser, API and browser together on a 16 GiB Mac | Gate reports (`resident_memory_mb`) |

### Capabilities not used

Tool or function calling, vision, embeddings from Qwen3-4B (the separate embedding model is in section 11),
thinking mode, contexts above 4,096 tokens, languages other than English, fine-tuning,
and any hosted model.

## 5. Calls per turn

A candidate turn makes three model calls, in this order: topic, tone, role-play. Measured
over 163 scripted turns (gate run 3, one slot, Apple M4):

| Call | Temperature / seed | Max output | Input tokens, median (p95) | Output tokens, median (p95) | Time, median (p95) |
|---|---|---|---|---|---|
| Topic (`casc-interpret-v1`) | 0 / 0 | 120 | 849 (955) | 37 (50) | 2.14 s (2.77 s) |
| Tone (`casc-tone-v1`) | 0 / 0 | 120 | 591 (602) | 36 (47) | 1.11 s (1.44 s) |
| Role-play (`casc-roleplay-v1`) | 0.3 / per turn | 120 | 769 (1,276) | 26 (38) | 1.55 s (2.93 s) |

- Every one of the 489 calls finished with `stop`; none hit the output cap or failed.
- Whole turn: median 4.9 s, p95 6.4 s. Nothing is shown until the whole reply has passed the
  output guard.
- Output speed is about 35 tokens per second (from the median timings above).
- Memory of the model server during the run: 3.9 GB resident, 1.6 GB footprint.

The topic and tone calls are independent of each other; the role-play call depends on
both, because the disclosure rules need the topics and the rapport level.

## 6. What the model is not trusted with

Each rule below is code wrapped around a model call. Each was added because the model
was measured to fail without it.

| Call | Deterministic rule |
|---|---|
| Topic | Sees topic labels, never fact content. An explicit "none of these" option. Unknown topic IDs are ignored. Failure releases nothing (fail closed). |
| Tone | Empathy must be quoted from a statement, not a question, in the trainee's line. "Specific" needs at least 8 quoted words. Confrontation needs quoted words, and a question that opens with a question word is never confrontational. Failure means no empathy. |
| Disclosure | Which facts are released, and when, is decided by `roleplay/disclosure.py` from the topic and tone results. The model never chooses. |
| Role-play | Sees only facts already released (vague wording until a follow-up). Output guard on the whole reply: stage directions and sheet tags removed; any character break replaces the reply with a case-authored deflection; unfinished sentences dropped; sentences already said dropped (unless first); sentences with a number not in the known facts, persona or question dropped. Character questions are appended verbatim by code. |

## 7. Failure handling

| Condition | Result |
|---|---|
| Server down or identity mismatch | Turn refused with HTTP 503; the session is unchanged |
| Topic call error, timeout or invalid JSON | Nothing released this turn (flag `interpretation_failed`); the reply still goes ahead |
| Tone call error, timeout or invalid JSON | Empathy 0, no confrontation (flag `tone_failed`) |
| Role-play call error or timeout (default 60 s per call) | Turn logged as `turn_failed`; the candidate sees an error and can resend |
| Reply truncated, empty or out of character | Guard removes it; a case deflection is used if nothing remains |

Each call's prompt version, model ID and revision, token counts, timings and finish reason
are written to the session log (`roleplay/calls.py`). Prompt text and audio are not stored.

## 8. Measured quality

These figures come from the evaluation scripts; each can be re-run.

| Measure | Result | Command |
|---|---|---|
| Topic selection, held-out labels | 98.5% exact match, 0 spurious selections | `npm run eval:interpreter` |
| Any empathy vs none, held-out tone labels | 92% (paper-v1: 93%) | `npm run eval:rapport` |
| Empathy level (0/1/2) | 82% | same |
| Confrontation precision / recall | 1.0 / 0.54 | same |
| Interpretation correct in scripted interviews | 93–94% | `npm run eval:fidelity -- --judge none` |
| Role-player leaks of locked facts | 0 in 489 turns | `npm run eval:leaks` |
| Replies with numbers not in the case | 0 in 489 turns | fidelity report |

Results and their history are in [REALISM-PLAN.md](REALISM-PLAN.md) and
[CASC-POC-PLAN.md](CASC-POC-PLAN.md). The 8B model was not better on these measures and
was about twice as slow.

## 9. Changing the model, runtime or settings

Any change to the model file, quantisation, runtime build, server flags or generation
options counts as a new configuration. Even at temperature 0, llama.cpp output can change
when batching or slot settings change. Before adopting it:

1. Pin it: update `config/model-register.json` or `config/native-runtime.json` with exact
   revision and checksum, and make sure `verify_service` checks it.
2. Run `npm run eval:interpreter` and `npm run eval:rapport -- --split test`. Topic
   selections should be unchanged, or the change reported.
3. Run three gate runs (`npm run eval:fidelity -- --judge none`) and `npm run eval:leaks`.
   Early disclosures, leaks and unsupported numbers must be no higher than before.
4. Record latency and `resident_memory_mb` against the 16 GiB budget, with the speech
   server running.
5. Record the configuration in results and in the paper. Results do not carry over from
   one configuration to another.

## 10. Open items

- **Two slots for parallel interpreter calls: tried and rejected (2026-10-08).** With two
  4,096-token slots and the topic and tone calls sent together, the median turn fell from
  4.92 s to 4.78 s (3%), but the role-play call got slower (1.55 s to 1.63 s). Model server
  memory rose from 3.9 GB to 5.9 GB resident and from 1.6 GB to 11.3 GB footprint. Topic
  selections were identical, but 137 of 163 replies changed, so every result would need
  re-measuring. The slot count stays at 1; it is now read from
  `config/native-runtime.json` (`parallel_slots`) by both the start script and the API check.
- **Prompt caching: measured, nothing adopted (2026-10-12).** Each call now logs the prompt
  tokens the runtime reused from its cache. At baseline the tone call reuses 565 of 591 tokens,
  the topic call 459 of 848 (1.11 s of prompt processing), role-play 429 of 782 (0.80 s).
  - Topic call reordered so the fixed parts are cached: interpreter 0.9–1.3 s faster, but
    held-out exact match fell from 98.5% to 94.1% with 4 spurious selections, in both
    layouts tried (station topics before the utterance; topics in the system message).
  - `--cache-reuse 256`: same accuracy, no speed gain (one slot is overwritten between calls).
  - Role-play with known facts and affect moved from the system message to the turn note:
    role-play prompt time 0.80 s to 0.61 s and turn p95 6.4 s to 5.6 s, but no change in the
    median turn. The topic call, which reads the character's previous reply, made more
    spurious selections (checklist precision 0.985 to 0.94–0.97). Rejected.
  Rejected prompts are kept in `artifacts/eval/rejected-prompts/`. Larger gains need the
  classifier interpreter (`docs/LLM-STATION-PROMPT.md`, Prompt C, is its first step).
- **Topic call is the main error source.** Every Phase 2 probe failure and checklist miss
  traced to a topic or tone misreading, not to the deterministic rules.

## 11. Embedding model (classifier interpreter)

Step 2 of the interpreter work adds a second, much smaller Qwen model. It embeds trainee
lines and topic labels for trained classifiers; it generates no text and never sees hidden
fact content. The classifier cascade is the default interpreter from tag `cascade-1`
(`INTERPRETER=cascade`); `INTERPRETER=model` restores the Qwen interpreter for every line.

| Item | Value |
|---|---|
| Model | Qwen3-Embedding-0.6B, GGUF `Q8_0`, revision `370f27d7550e0def9b39c1f16d3fbaa13aa67728` |
| File | `Qwen3-Embedding-0.6B-Q8_0.gguf`, 639,150,592 bytes, SHA-256 `06507c7b…c3e439` |
| Server | Same pinned `llama-server`, started and stopped with the generation model by `npm run models:start`; 127.0.0.1:8181; `--embedding --pooling last`, one slot of 4,096 tokens |
| Identity check | `verify_embedding_service`: model path, build, alias, slots and context, as for generation |
| Output | 1,024 dimensions, L2-normalised by the adapter (`LocalEmbeddingModel`) |

Measured on the Apple M4 (2026-10-13): one trainee line embeds in a median 33 ms (max 54 ms,
20 lines); a case's 48 topic labels embed in 0.69 s, once per station. The embedding server
uses 1.1 GB resident and 0.6 GB footprint; with Qwen3-4B (3.0 GB resident, 0.7 GB footprint
after start-up) and Whisper (about 0.1 GB resident, 0.7 GB footprint in earlier runs), the
three servers come to about 4.2 GB resident.

Plain cosine similarity between a line and topic labels is not enough on its own (for "Did
you leave a note for anyone?", the label "note" tied with "who found you").

### Step 2c: offline classifier results (2026-10-13, development data only)

`npm run eval:classifier` trains on `data/training/`, picks accept-or-defer thresholds on
5-fold out-of-fold training predictions, and checks them on the development label sets. A
line the classifier is not confident about goes to the existing Qwen call; Qwen's recorded
development answers stand in for those calls. The held-out test sets were not read.

Design chosen, after comparing alternatives on out-of-fold training data:

| Topic classifier (per case: each fact plus "no topic") | First choice correct | Lines decidable at 98.5% exact |
|---|---|---|
| Embeddings only, with Qwen3-Embedding's instruction prefix | 85% | 21% |
| Embeddings only, no instruction | 86% | 32% |
| Word and character n-grams only | 69% | 16% |
| **Embeddings + n-grams, no instruction (chosen)** | **86%** | **40%** |
| One scorer for all cases, tested on a case it never saw | n/a | under 1% |

A new station therefore needs its own training lines (Prompt C) before the classifier can be
used for it. Tone heads use the same features; n-grams raised out-of-fold accuracy from
82–88% to 90–91% (empathy) and 87–91% to 92–93% (confrontation).

Results at the chosen thresholds (topic 0.9; tone 0.8). Two-question lines always defer.

| | Classifier decides | Correct when it decides | Cascade (classifier, else Qwen) | Qwen alone |
|---|---|---|---|---|
| Topic, out-of-fold (952 training lines) | 31% | 99.0% exact; 3 wrong selections | n/a | n/a |
| Topic, development (27 lines) | 15 | 15/15; 0 wrong selections | 25/27 exact; 2 wrong selections | 25/27; 2 wrong selections |
| Tone, out-of-fold (400 lines) | 72% | no false empathy or confrontation; 2 confrontations missed | n/a | n/a |
| Tone, development (20 lines) | 12 | 12/12 | any empathy 20/20, level 18/20, confrontation found 4/5 | 19/20, 17/20, 3/5 |

Deferred development lines were the expected kinds: follow-ups that need the previous
exchange, summaries and empathic statements that mention a topic, and two-question lines.
The development sets are small (27 and 20 lines), so these are indications only; the
held-out sets and scripted gate runs decide (step 2e).

### Step 2d: the cascade interpreter (2026-10-13)

`INTERPRETER=cascade` (the default from tag `cascade-1`) replaces the Qwen interpreter with
`CascadeInterpreter` (`roleplay/classify.py`):

- The classifiers are trained once per API process, on first use, from `data/training/`
  (about a second with the cached training embeddings in `artifacts/classifier/`).
  Trainee lines are embedded at runtime but never cached or stored.
- Topic: the case's classifier answers if its confidence is at least 0.9 and the line has
  fewer than two question marks; otherwise the Qwen topic call runs. A case without
  training lines always uses Qwen.
- Tone: the classifier answers if both heads are at least 0.8 confident and no character
  question is pending; otherwise the Qwen tone call runs. The deterministic tone rules
  (statements only, eight words for specific, no confrontational plain questions) apply
  to both routes.
- If the embedding server is unavailable, the turn runs exactly as with the Qwen
  interpreter and is flagged `classifier_unavailable`.
- Each turn logs `topic_route`, `tone_route` (`classifier` or `model`) and the
  classifiers' confidences. The session's interpreter version is
  `classifier-v1-<training data hash>+casc-interpret-v1+casc-tone-v1`.
- Evaluation scripts take `--interpreter cascade` (the default) or `--interpreter model`
  (`eval:interpreter`, `eval:rapport`, `eval:fidelity`).

Live check on the 27 development topic lines: identical to the 2c simulation (25/27 exact,
2 spurious, both Qwen's). The classifier decided 15 topics and 25 tones; interpretation
averaged 1.3 s against about 3.5 s, and lines decided entirely by the classifiers took
45–55 ms. A pure empathy statement ("That sounds really hard.") still defers its topic
(confidence 0.36), so such lines save only the tone call; a possible later improvement.

### Step 2e: evaluation of the cascade (2026-10-13)

Held-out label sets, run once (`eval:interpreter --split test --interpreter cascade`,
`eval:rapport --split test --interpreter cascade`):

| Held-out measure | Qwen interpreter | Cascade |
|---|---|---|
| Topic exact match | 98.5% | 98.5% (its one miss is on a line deferred to Qwen) |
| Spurious topic selections | 0 | 0 |
| Topic lines decided by the classifier | n/a | 43 of 68 (63%) |
| Interpretation time, mean | about 2.8–3.1 s | 0.77 s |
| Any empathy vs none | 92% | 95% |
| Empathy false positives / negatives | 2 / 3 | 1 / 2 |
| Empathy level accuracy | 82% | 92% |
| Confrontation precision / recall | 1.0 / 0.54 | 1.0 / 0.46 |
| Tone lines decided by the classifier | n/a | 41 of 60 |

The cascade and Qwen differ on one confrontational line: "Stop talking for a moment and
answer my question." (Qwen flagged it; the classifier was confident it was not
confrontational). Recall falls one line short of the bar, on a set of 13.

Three scripted gate runs (`eval:fidelity --judge none --interpreter cascade`, 163 turns
each) against the Qwen-only runs of the same scripts:

| Measure | Qwen interpreter | Cascade, runs 1–3 |
|---|---|---|
| **Turn median / p95** | 4.93 s / 6.43 s | **2.84–2.99 s / 5.67–6.08 s** |
| Interpretation median | 3.28 s | 1.72–1.77 s |
| Topic and tone decided by the classifier | n/a | 47% and 87% of turns |
| Interpretation correct (128 original turns) | 93.8–94.5% | 95.3–96.1% |
| Checklist precision / recall | 0.985 / 0.94–0.97 | 1.0 / 0.956–0.971 |
| Replies with a number not in the case | 0 | 0, 0, 0 |
| Leak-screen flags | 0–1 | 0, 2, 0 |
| Probes: early rapport, follow-up, rapport level | 4/5, 8–10/10, 3/4 | 4/5, 8–10/10, 3/4 |
| Probes: character question, answered, affect | 2/3, 2/3, 4/6 | 3/3, 3/3, 4/6 |

Both leak-screen flags were on turns the classifier deferred: the Qwen topic call read
"Usually every week at first..." as asking about Daniel's fear of needles, and "How did he
get on with his last medication?" as asking about adherence, the same misreadings seen in
Qwen-only runs. No fact was released by a classifier decision that the script did not ask
for (checklist precision 1.0 in every run).

Memory with all three servers running: Qwen3-4B 3.6–4.1 GB resident, embedding 1.1 GB,
Whisper under 0.1 GB, so about 4.8–5.2 GB resident. The generation server's footprint grew
from 6.1 GB to 9.2 GB over the three runs; Qwen-only runs show the same growth (5.2 GB in a
Qwen-only run). It is llama.cpp's host-memory prompt cache (`--cache-ram`, default up to
8 GB), not the cascade, and is worth capping separately.

Outcome: the cascade cuts the median turn by about 40% (4.9 s to 2.9 s) and meets every
bar except held-out confrontation recall, which is one line short. Adopted as the default
interpreter on 2026-10-13 (tag `cascade-1`). On the gate it released no more facts by
mistake than the Qwen interpreter, and improved interpretation, checklist precision and the
character-question probes.

### Tag `cascade-2` (2026-10-13): impatient lines and a capped prompt cache

- **Tone training.** Fifteen impatient or pressuring lines (three per case) were added to
  `data/training/tone/` after the held-out miss above. Re-applying the threshold rule moved
  the tone threshold from 0.8 to 0.85 (at 0.8 the retrained heads gave two false empathy
  ratings out of fold). Held-out tone afterwards: any empathy 95%, level 93%, one false
  positive, confrontation recall 0.54 (precision 1.0). This recall is not an unbiased
  estimate, because the gap that prompted the change was found on a held-out line; the clean
  figure is 0.46 above. The classifier now decides 36 of 60 held-out tone lines (41 before).
- **Prompt cache capped** at 1024 MiB (`--cache-ram`).
- **Gate, three runs:** median turn 2.85–2.93 s (p95 5.59–5.84 s); interpretation correct
  95.3%; checklist precision 1.0, 0.985, 1.0, the one extra release coming from the Qwen
  topic call ("Daniel has been aggressive at home, hasn't he?" read as asking for his view);
  no unsupported numbers; one leak-screen flag, the familiar Qwen misreading about needles;
  probes as `cascade-1`. Qwen's server footprint stayed at 1.7 GB (6.1–9.2 GB before the cap),
  with no latency cost; the three servers together use about 5 GB resident and 2.9 GB
  footprint.

Training data: `data/training/` (topic: 971 lines; tone: 415 lines, including the 15 added
for `cascade-2`), drafted with Prompts C and D in [LLM-STATION-PROMPT.md](LLM-STATION-PROMPT.md).

## Licence and approval

Qwen3-4B is Apache-2.0 (verified 2026-09-25 from the publisher's licence file). Legal review
is pending, and the register records `release_approved: false`. Downloading the weights for
local evaluation is not approval to redistribute them or release the software
(`config/model-policy.json`).
