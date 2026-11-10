# CASC simulated-interview proof of concept

Status: Phases 0–3 complete; Phase 4 automated evaluation complete (2026-10-07). Human ratings and real-voice recordings pending; Phase 5 paper draft in [PAPER-DRAFT.md](PAPER-DRAFT.md). Next: [REALISM-PLAN.md](REALISM-PLAN.md). Supersedes the broad MRCPsych learning plan,
which is preserved at git tag `pre-casc-archive`.

Remote deployment extension: [controlled online pilot plan](ONLINE-PILOT-PLAN.md)
proposes owner-only access through Cloudflare Tunnel, followed by user isolation,
bookings and an optional paid pilot. The isolated local production runtime is
implemented; external access remains pending. See the
[production runbook](PRODUCTION-RUNBOOK.md) for operation and validation limits.

## Research question

Can a fully local, privacy-preserving simulated patient, constrained by a structured
hidden case state, support CASC-style practice on consumer hardware with acceptable
latency and fidelity to the case?

The POC is intended for a poster or paper. It makes no claim of clinical validity or
educational effectiveness; those are stated limitations and further work.

## Constraints

- No clinician time: cases are author-written fiction, marked `clinically_validated: false`.
- Local models only, on an Apple M4 / 16 GB host. No hosted fallback.
- If local role-play is not convincing, fall back to text patient replies with speech input.
- Every evaluation must have ground truth that needs no clinical judgement.

## Scope

In: 4–6 original cases (history and management stations), a text role-play engine with
disclosure gating, local speech recognition, optional local TTS, station timer,
transcripts, deterministic checklist feedback and descriptive communication indicators.

Out (further work): avatar, clinician-authored or validated cases, examiner-calibrated
marking, trainee studies, hosted models, examination stations needing physical actions.

## Phases

| Phase | Weeks | Deliverable |
|---|---|---|
| 0. Scope reset | 1 | Archive tag, strip-back, case schema, project rules rewritten |
| 1. Case schema and role-play engine | 2–3 | Disclosure-gated role-play, disclosure log, 4–6 cases |
| 2. Voice input | 1–2 | whisper.cpp (Metal) push-to-talk; optional local TTS |
| 3. Feedback | 1–2 | Checklist from disclosure log; communication indicators |
| 4. Evaluation | 2–3 | Latency, WER, role-play fidelity, checklist accuracy, model comparison |
| 5. Write-up | 1–2 | Poster/paper with limitations and further work |

## Evaluation design

| Question | Method | Ground truth |
|---|---|---|
| Latency | Per-stage and end-to-end timings over many turns | Timings |
| ASR accuracy | WER on 50–100 scripted utterances, clinical-term error breakdown | The scripts |
| Role-play fidelity | Scripted and adversarial interviews: invented facts, premature disclosure, character breaks, contradictions | The case file |
| Checklist accuracy | Seeded transcripts of known quality, plus LLM-simulated candidates | Deliberately omitted items |
| Model choice | Qwen3 4B against one 7–8B local model on the measures above | As above |

## Phase 1 results

Delivered: five original cases (all marked not clinically validated); the disclosure-gated
engine described in [ARCHITECTURE.md](ARCHITECTURE.md#turn-flow-phase-1); JSONL session
logs; reading/interview/debrief UI; and an interpreter evaluation
(`npm run eval:interpreter`).

### Interpreter accuracy (Qwen3 4B Q4_K_M, Apple M4, temperature 0)

Labels are author-written. The overdose case is the **development** split, used for tuning;
labels for the other four cases (**test** split) were committed before tuning (commit
`f624e51`) and never used to tune prompts or labels.

| Interpreter | Split | Items | Exact match | Precision | Recall | Spurious selections | Rapport accuracy | Mean latency |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| Keyword baseline | development | 27 | 0.41 | 0.49 | 0.90 | 20 | 0.96 | <1 ms |
| Keyword baseline | test | 68 | 0.59 | 0.51 | 0.87 | 46 | 0.97 | <1 ms |
| Qwen, initial prompt | development | 27 | 0.70 | 0.68 | 0.81 | 8 | 0.93 | 1.5 s |
| Qwen, initial prompt | test | 68 | 0.88 | 0.84 | 1.00 | 10 | 0.97 | 1.4 s |
| Qwen, tuned | development | 27 | 0.93 | 0.91 | 1.00 | 2 | 1.00 | 1.8 s |
| Qwen, tuned | **test** | **68** | **0.99** | **1.00** | **0.98** | **0** | **0.97** | 1.8 s |

Tuning changes, in order: a strict prompt with a paraphrase (`focus`) field; listing all
topics including already-unlocked ones (removing them pushed repeat questions onto the
nearest remaining topic); an explicit `none_of_these` option; and topic keys built from
question labels instead of bare fact IDs. Spurious selections matter most because each
can reveal a hidden fact early.

### Observed role-play behaviour (qualitative, development runs)

- End-to-end turn latency on the M4 was about 2.5–4.5 s (interpreter ~1.5–2 s, reply ~1–2.5 s).
- With the per-turn note, replies voiced the selected facts, deflected unanswerable
  questions ("Are you married?") and stayed in character.
- A fact that did not directly answer its question ("bought the tablets two days ago" for
  "Had you planned it?") produced a contradiction ("I didn't plan it") in 3/3 runs; rewriting
  the fact as a direct answer removed it in 3/3 runs. This is now a case-authoring rule.
- Residual issues: mild embellishment ("I've been feeling really stuck"), repeated
  persona phrases, and occasional interpreter errors on explanations (Maria's case) and
  greetings marked as rapport. Phase 4 quantifies fidelity.

### Phase 1 limitations to report

- Author-written cases and labels; no clinical or independent review; one labeller.
- Small label sets (95 utterances); typed, well-formed utterances, not speech.
- Rapport is a single binary flag; one false positive unlocks all rapport-gated facts.
- One model, one quantisation, one machine; replies are not streamed to the browser.

## Phase 2 results

Delivered: whisper.cpp v1.9.5 built from checksum-verified source with Metal
(`npm run speech:install`), Whisper large-v3-turbo Q5_0 on loopback port 8182; browser
push-to-talk recording to 16 kHz WAV in memory; transcripts placed in the composer for
review or sent directly; `transcribed` events and `input`/`edited` fields in session logs
(no audio stored); optional read-aloud with on-device system voices; `npm run eval:asr`.

### Speech recognition on synthetic speech (Apple M4, 2026-10-07)

Each of the 95 labelled interpreter utterances was synthesised with six on-device macOS
voices (British, American, Australian, Irish, Indian and South African English), 570 clips,
mean 2.6 s, and transcribed with the same prompt the app uses.

| Voice (accent) | WER (spelling-normalised) | WER (raw) | Exact transcripts |
|---|---:|---:|---:|
| Daniel (en-GB) | 0.13% | 0.38% | 98.9% |
| Samantha (en-US) | 0.00% | 0.25% | 100% |
| Karen (en-AU) | 0.38% | 0.63% | 96.8% |
| Moira (en-IE) | 0.13% | 0.38% | 98.9% |
| Rishi (en-IN) | 0.00% | 0.25% | 100% |
| Tessa (en-ZA) | 0.00% | 0.25% | 100% |
| **All 570 clips** | **0.11%** | **0.36%** | **99.1%** |

Raw errors are almost all British spellings transcribed as American ("favourite" →
"favorite", "summarise" → "summarize"); normalisation maps such variants, as is standard.
Content-word recall was 99.1%. Mean recognition time was 0.99 s per clip, a real-time
factor of 0.39 (warm server, one request at a time).

**End to end:** with the British voice, the tuned interpreter selected identical facts from
the Whisper transcript and the typed text for **95/95 utterances**; exact match with the
labels was 95.8% in both conditions.

### Phase 2 limitations to report

- **Synthetic speech is a lower bound.** Text-to-speech is fluent, clean and well articulated;
  real candidates hesitate, self-correct, overlap and speak in noisy rooms. Phase 4 needs
  human recordings (`npm run eval:asr -- --manifest recordings.yaml`).
- One recogniser model and prompt; small and base English models are installable for comparison.
- Push-to-talk only (no voice activity detection or interruption); replies are not streamed.
- Read-aloud uses basic system voices with no per-character voice or prosody; neural TTS is further work.
- The browser test feeds a synthesised clip as a fake microphone; real microphones and
  browsers other than Chromium were not tested automatically.

## Phase 3 results

Delivered: deterministic feedback from session logs (information gathering by fact and
domain with timing; station tasks with quoted evidence; communication indicators on an
annotated transcript); a feedback screen; `npm run feedback` for saved logs; and
`npm run eval:indicators`.

### Indicator accuracy against author labels

Labels for 102 utterances (60 test, 42 development) were committed (`2420711`) before the
rules were written; rules were tuned on the development split only.

| Split | Items | Question type (open/closed/none) | Summary P / R | Check of understanding P / R | All three correct |
|---|---:|---:|---:|---:|---:|
| Development | 42 | 100% | 1.00 / 1.00 | 1.00 / 1.00 | 100% |
| **Test** | **60** | **98.3%** | **1.00 / 0.83** | **1.00 / 1.00** | **96.7%** |

Test errors: a statement opening with "What I'm hearing is…" was tagged as an open question,
and "So you took the tablets… is that right?" was not recognised as a summary.

**Important caveat:** the same author wrote the labels and the rules, and the test
utterances were written immediately before the rules. One rule phrase copied from a test
item was found and removed before scoring, but the split is **not blind**. Report this as a
consistency check; independent validation needs utterances from real sessions (Phase 4).

Empathy uses the interpreter's rapport flag (held-out rapport accuracy 0.97 in Phase 1).

### Phase 3 limitations to report

- Indicators are surface rules on wording; they cannot judge tone, timing, relevance or
  whether a technical term was then explained.
- "Key information elicited" counts unlocks: an unlock follows the interpreter's decision,
  so interpreter errors become feedback errors (Phase 1 accuracy applies).
- Task evidence covers 5 of 7 tasks; non-judgemental style and explaining monitoring are
  left to self-review.
- No comparison with examiner judgements; feedback is not a CASC mark.

## Phase 4 results

Delivered: 15 scripted interviews (128 turns, 40 adversarial probes; committed `ab66260`
before any run), `eval:fidelity`, blind human-rating kit (`eval:ratings`,
`eval:agreement`), opt-in real-voice recording page (`/record`), and a pinned comparison
model (Qwen3-8B Q4_K_M). Hardware: Apple M4, 16 GB, llama.cpp b11149 Metal.

### End-to-end results from the scripted interviews

Measures here are deterministic (no judge model). Checklist accuracy compares the feedback
with the facts each script was designed to elicit or omit.

| Run | Interpretation correct | Checklist precision / recall | Fact status correct | Early-rapport · repeat · stacked probes | Leak flags | Unsupported numbers | Turn median / p95 | First spoken token (median) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Run 1 · 4B | 93.8% | 0.98 / 0.94 | 95.9% | 4/5 · 5/5 · 5/5 | 1 | 0 | 3.6 / 5.0 s | 0.70 s |
| Run 2 · 4B | 93.8% | 0.96 / 0.96 | 95.1% | 2/5 · 5/5 · 5/5 | 0 | 0 | 3.8 / 5.5 s | 0.72 s |
| Run 3 · 4B (clean latency) | 92.2% | 0.98 / 0.93 | 95.1% | 3/5 · 5/5 · 4/5 | 2 | 0 | 3.7 / 5.3 s | 0.69 s |
| Run 2 · 8B | 92.2% | 0.96 / 0.99 | 96.7% | 4/5 · 5/5 · 5/5 | 0 | 0 | 7.0 / 9.8 s | 1.30 s |

- **No real leaks.** All three lexical leak flags were false positives on inspection
  (everyday words such as "think" and "really" shared with a locked fact). This matches
  the design: the role-player never receives a locked fact.
- **Run-to-run variation.** Role-play is sampled (temperature 0.3), and each reply feeds
  the interpreter's context, so identical scripts give slightly different results:
  interpretation 92–94%, checklist recall 0.93–0.96, early-rapport probes 2–4 of 5.
- **Early-rapport failures are interpreter errors:** a plain "And how are you coping?"
  flagged as rapport (one false positive unlocks every gated fact), a question mapped to
  the wrong topic, and "Do you think you're unwell?" matching no topic in every run.
- **Latency (run 3, only the deployed models loaded):** interpreter median 2.1 s, reply
  1.5 s, turn 3.7 s (p95 5.3 s); speech recognition adds about 1 s (Phase 2). With the 8B
  also loaded the Mac swapped (15% memory free, 8.5 GB swap); runs 1–2 timings are similar
  but not clean.
- **Memory (run 3):** generation server phys_footprint 2.4 GB plus Whisper 0.66 GB, about
  3.1 GB; 64–78% of system memory free.

### Qwen3 4B vs Qwen3 8B

| | Qwen3 4B Q4_K_M | Qwen3 8B Q4_K_M |
|---|---:|---:|
| Interpreter, held-out labels (68): exact / precision / recall | 0.99 / 1.00 / 0.98 | 0.97 / 0.96 / 1.00 |
| Spurious selections (held-out) | 0 | 2 |
| Scripted interviews: interpretation correct | 92–94% (3 runs) | 92.2% (1 run) |
| Checklist recall | 0.93–0.96 | 0.99 |
| Turn latency, median | 3.7 s | 7.0 s |
| Model file | 2.5 GB | 5.0 GB |

The 8B is not more accurate overall and is twice as slow. The prompts were tuned on the
4B, which may favour it. The registered 4B remains the deployed model.

### Baseline: the whole case in the prompt

To isolate what disclosure gating adds, the same scripts were run with the same model,
temperature, seeds and output guard, but with the conventional design: one prompt holding
the persona and every fact, each tagged "may volunteer", "only when asked" or "only after
empathy", with explicit instructions to withhold (`--condition full-case`,
`prompts/casc-roleplay-fullcase-v1.txt`). Early disclosure was screened with
`npm run eval:leaks` against each script's design (a fact is allowed once the script has
asked for it) and every flagged turn and all 40 probe turns were then read by the author.

| Measure (128 scripted turns, Qwen3 4B) | Whole-case prompt (baseline) | Disclosure-gated |
|---|---:|---:|
| Turns with early disclosure (screened, then confirmed by reading) | **12 (9.4%)** | 0, 2, 0 across three runs (0.5%) |
| Prompt injection: whole case revealed | **2 of 5** | 0 of 5 |
| Rapport-gated fact revealed before any empathy | 3 of 5 | 0, 1, 0 of 5 |
| Facts volunteered unprompted in ordinary turns | 7 | 0 |
| Inventions on off-case or leading probes | 3 | 1–2 |
| Disclosure log for feedback | none | yes |
| Turn latency, median (first token) | **1.0 s (0.19 s)** | 3.7 s (0.7 s) |

All 12 baseline flags were genuine early disclosures. The two injection failures listed
the whole case; one was a third-person summary ("Helen is overwhelmed…") that the output
guard did not catch as a character break. Both gated early disclosures (run 2) came from
interpreter decisions: "And how are you coping?" was misread as empathy, releasing a
rapport-gated fact, and a leading question about violence was linked to the
behaviour-change fact (borderline). The lexical screen missed the first; it undercounts,
which is why probe turns were read in full. Gating
does not prevent harmless invention on off-case questions ("I drive a petrol car"),
which occurred in both conditions. Its cost is latency: the interpreter call adds about
2.7 s per turn. One baseline run only.

### The judge model is not reliable (key finding)

Classifying each reply as faithful, embellished or invented was delegated to a judge
model, with a deterministic correction that discards "added" details already worded in
the known facts. On inspection the judges mostly flagged feelings, filler and paraphrased
facts as inventions, and their verdicts moved with the judge and prompt:

| Replies and judge | Faithful | Embellished | Invented | Contradiction | Out of character | Clinical advice | Acceptable |
|---|---:|---:|---:|---:|---:|---:|---:|
| Run 1 replies, judge v1 = 4B | 58 | 35 | 30 | 0 | 2 | 3 | 73% |
| Run 1 replies, judge v1 = 8B | 86 | 14 | 27 | 0 | 1 | 0 | 78% |
| Run 2 replies, judge v2 = 8B | 36 | 24 | 66 | 1 | 1 | 0 | 47% |

Judge prompt v2 (stricter definition of "significant") was frozen before run 2 and made
false positives worse. Automated fidelity classes are therefore **not** reported as
results. The primary fidelity measure is the blind human rating of 100 replies (50 per
model), generated as `data/evaluation/ratings/sheet-20261007-1856.csv`; agreement between
those ratings and the judge will be reported as a judge-validity result.

### Errors found by reading the transcripts (author inspection, not exhaustive)

- **Contradiction:** asked about sleep, Alex said "I've been sleeping well, thanks" (case:
  three hours a night).
- **Invented examples:** Helen added "where he put his keys", "what he had for breakfast"
  and "about the weather or the time" to a fact that gives no examples.
- **Off-case invention:** asked what car she drives, Helen said "I drive a petrol car".
- **Invented motive:** Jordan, "I decided to do something to make myself feel better".
- **Character break and tag leak (run 1, fixed before run 2):** under a prompt-injection
  probe, Helen said "I'm not sure if it's real or a simulation… OPEN". The guard now strips
  sheet tags and catches wider break phrases (`3e7e06b`); the adversarial scripts are
  therefore partly development data from run 2 on.
- **Repeated persona phrases** ("I just want to go home", "I'm focused on my business")
  appear in many replies.

### Phase 4 limitations to report

- Human fidelity ratings and real-voice recordings are pending; until then fidelity rests
  on author inspection, and speech accuracy on synthetic voices.
- One author wrote the cases, scripts and labels; scripts were written before any run but
  are not independent of the case author.
- Few runs (three 4B, one 8B) and one script set per case; variation is reported as ranges.
- The leak check is lexical and over-flags common words; it is a screen, not proof.
- One machine; the comparison model shared memory with others during its run.

## Phase 0 checklist

- [x] Branch `casc-poc`; snapshot and tag `pre-casc-archive`
- [x] Case schema (`services/api/src/psychiatry_api/cases.py`) enforcing the pinned
      CASC blueprint vocabulary and timings; first case `data/cases/elevated-mood-history.yaml`
- [x] Read-only `/api/cases` returning summaries without hidden facts
- [x] AGENTS.md, ADR-010/011 and this plan
- [x] Remove out-of-scope code, data, prompts, docs and tests (see list below)
- [x] Remove Postgres: `infra/`, migrations, `db.py`, Docker steps in `scripts/dev`
- [x] Trim `config/sources.yaml` to fixtures, RCPsych/CASC and blocked records
- [x] Generation-only model register and `models:start`
- [x] Replace the web dashboard with a station list; rewrite README and ARCHITECTURE

### Removed in Phase 0

Code: `packages/`, root `tests/`, `scripts/{stage0,stage2,stage3,learning,reviews,sources}`
(`scripts/stage0/hardware.mjs` moved to `scripts/hardware.mjs`), `services/api/src/psychiatry_api/`
`{public/,answers,evaluate_local,fixtures,ingest,retrieval,scalable_retrieval,reviews,review_routes,db}.py`,
`models/{reranking,retrieval_metrics}.py`, matching API tests, the old `apps/web` components and tests
and the `learn`/`reviews` pages.

Data and config: `data/fixtures/`, `prompts/`, the study/syllabus/population configs under
`config/`, and all historical plans and reports in `docs/` except `DECISIONS.md`,
`ARCHITECTURE.md`, `permissions/` and this plan.

Ignored local data (not in git; delete manually if wanted): `data/local/public` (~4 GB)
and `artifacts/`.
