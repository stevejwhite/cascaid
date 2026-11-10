# Student interpreter: a small fine-tuned model for topic and tone

Status: 2026-10-20: run 6 is the served student, with the cross-check rule
(`STUDENT_CROSS_CHECK=all`, docs/STUDENT-CROSS-CHECK-PLAN.md); it decides topics only; tone
stays with the classifiers and Qwen.

## Why

On logged sessions, a turn decided by the classifiers takes a median 1.4 s; a turn that
needs Qwen3-4B takes 3.9 s, of which 2.4 s is interpretation (two calls: topics, then tone)
and 1.3 s the reply. Interpretation is labelling, not writing, and a 4B general model is
more than it needs. A 0.6B to 1.7B model fine-tuned for exactly this job, with the case's
topics in its prompt and the previous exchange for context, should answer both questions in
one call in a few hundred milliseconds. Qwen3-4B stays as teacher and fallback until the
student matches it on the held-out tests.

## Design

- **Base models:** Qwen3-0.6B and Qwen3-1.7B (Apache-2.0; the same family and tokenizer as
  the current model), pinned by revision in `config/finetune.json` and checked file by file
  against Hugging Face's SHA-256 records.
- **Training:** LoRA with MLX on this Mac (`tools/finetune`, mlx 0.32.3 and mlx-lm 0.32.0,
  MIT, locked with uv). Loss on the answer only (`mask_prompt`).
- **One call, one format** (`psychiatry_api/finetune/format.py`, shared by training and the
  future runtime): the case's topic keys and labels (the same keys Qwen is shown), the
  previous exchange, the line; the answer is JSON with the topic keys, empathy level and
  the quoted empathy words, confrontation and the quoted words. The runtime's deterministic
  rules (quoted, graded, challenging) apply to the student exactly as to Qwen. An invalid
  answer falls back to Qwen.
- **Case-general:** topics come from the case file in the prompt, so a new station needs no
  retraining, only evaluation.

## Data

| Source | Topics label | Tone label | Context | Committed? |
|---|---|---|---|---|
| Topic training lines (`data/training/topics`, 1,370) | authored | Qwen3-4B teacher | follow-ups only | yes |
| Tone training lines (`data/training/tone`, 415) | Qwen3-4B teacher | authored | none | yes |
| Synthetic interviews (`data/finetune/synthetic`, Prompt E) | frontier LLM, by the runtime rules | frontier LLM | every turn | after review |
| Real sessions (`data/sessions`), two in three sessions | Qwen3-4B (logged) | Qwen3-4B teacher | every turn | **no**: `artifacts/` only |

Teacher labels for authored lines are cached in `data/finetune/teacher-labels.jsonl`; a
test ensures that file holds nothing but authored training lines. Teacher labels for
session lines go to `artifacts/finetune/teacher-sessions.jsonl`, which is not committed.

**Transcripts.** AGENTS.md rule 5 keeps transcripts local. Real sessions are therefore
labelled on this machine only, and Prompt E forbids the frontier LLM from reading
`data/sessions/`. Giving real transcripts to a hosted model would need a deliberate
decision recorded here first.

## Evaluation (all reproducible, no clinical judgement)

| Set | What | Gate for adopting the student |
|---|---|---|
| Topic development split (27 lines, with context) | exact sets, spurious, missed | exact ≥ Qwen (25), spurious ≤ Qwen (2) |
| Rapport development split | empathy level, false empathy, confrontation | no false empathy; confrontation found ≥ Qwen |
| Field set: one in three real sessions, held out | agreement with Qwen's logged topics | reported |
| Held-out test splits (topics and rapport) | as above | run once, at the end |
| Latency | median per call | ≤ 0.5 s |

Commands: `npm run finetune:label`, `npm run finetune:export`,
`tools/finetune/train.sh qwen3-0.6b`, `tools/finetune/predict.py`, `npm run finetune:score`.

## Integration: the student decides topics (2026-10-14)

`npm run student:install -- student-0.6b-v3` pins the 4-bit model by checksum in
`config/finetune.json` (the weights stay on this machine: they were trained partly on local
sessions); `npm run student:start` serves it with `mlx_lm.server` on 127.0.0.1:8184.
`psychiatry_api.models.student` is the adapter; the cascade (`cascade-v2`) asks it about
lines the topic classifiers are unsure of. Each turn logs the student call (format version,
weights checksum, time) and `topic_route: student`. The `pace` forecast asks the student
once (reused by the interpretation), so a hand-off to Qwen is announced as a slow turn.

**Rules learned in evaluation.** The student's answer is used only when it fits the line:

| The line... | Student says... | Then |
|---|---|---|
| has two questions ("Do you smoke, and how is your appetite?") | (not asked) | Qwen: the student labelled only one of the two |
| asks for information | a topic | the student's topic |
| asks for information | none, and the classifiers lean to none | none |
| asks for information | none, classifiers lean to a topic | Qwen (held-out test: all three student misses) |
| is a statement or leading tag question | none | none (nothing is released) |
| is a statement or leading tag question | a topic | Qwen (fidelity scripts: wrong early releases) |

These rules were motivated by the first test-split run and the fidelity scripts, so the
later figures on those sets are **post hoc**.

**Results.**

| Measure | Qwen decides topics | Student, first run (clean) | Student with the rules |
|---|---|---|---|
| Topic test split exact, spurious | 67/68, 0 | 65/68, 0 | 67/68, 0 (post hoc) |
| Topic test split mean interpretation | 670 ms | 209 ms | 360 ms |
| Topic development split exact, spurious | 25/27, 2 | 26/27, 0 | 26/27, 1 (Qwen's error) |
| Fidelity interpretation correct | 93.3, 93.9, 93.3% | 91.4% | 96.3, 96.3, 96.3% (post hoc) |
| Fidelity checklist precision / recall | 0.98–0.99 / 0.975 | 0.975 / 0.95 | 0.99–1.00 / 0.975 |
| Fidelity possible leaks, unsupported numbers | 0, 0 | 1, 0 | 0, 0 |
| Fidelity median turn (p95) | 2.85–2.93 s (5.6–5.8) | 2.01 s (4.5) | 1.92–2.10 s (5.0–5.6) |
| Hands-free: reply audible after end of speech | 4.4 s | — | **3.7 s** |

The leak analysis (`eval:leaks`) flags one turn in some runs of both conditions (a
needle-fear answer the script asked for), at the same rate. Before the rules, the student
caused two genuine early releases in one run (a topic for a leading question, then repeated
under a prompt-injection probe); the rules removed them.

## Run 4: with the Prompt E interviews (2026-10-14) — not adopted

Data: 2,858 training lines, 1,211 of them with the previous exchange (about 180 before),
adding Codex's 1,200 synthetic turns (60 interviews, unreviewed; 975 distinct lines; topic
labels agree with Qwen3-4B on 107 of 120 sampled turns, most disagreements being follow-ups
where Codex reads the context and Qwen does not). 900 steps, about 90 minutes (gradient
checkpointing is needed when all servers are running; without it the run ran out of GPU
memory).

| | Run 3 | Run 4 |
|---|---|---|
| Student alone: topic lines exact / spurious | 25/27, 0 | 26/27, 1 |
| Student alone: empathy detected / level | 15/20, 15/20 | **20/20, 17/20** |
| Student alone: confrontation found / false | 4/5, 3 | 1/5, **0** |
| Cascade: development exact / spurious | 26/27, 1 (Qwen's) | 25/27, 2 |
| Cascade: test exact / spurious (post hoc) | 67/68, 0 | 67/68, **1** |

Run 4 reads empathy much better and no longer mistakes warm reflections for confrontation,
but finds little confrontation (the interviews hold 15 confrontational lines against 120
empathic ones), and in the cascade it releases two facts wrongly: "Is this the first time
you've taken an overdose?" as the overdose details, and "Where does Daniel work?" (a
near-miss question no fact covers) as Daniel's views. Wrong releases matter most, so run 3
stays the served student. Next data should add near-miss questions (asking about something
no fact holds, with a fact's obvious words) and more confrontational lines in context.

## Run 5: with the Prompt F hard cases (2026-10-14) — not adopted

Run by Codex (the training request was made by mistake after Prompt F), with its own
pipeline in `artifacts/finetune/runs/student-0.6b-v5-prompt-f-20261014`: the same settings
as run 4, 1,300 steps over 4,079 lines (Prompt F's 806 turns repeated to 1,241 rows; 924
confrontational rows). It changed nothing in the app. Its data-building code is not in the
repository.

| | Run 3 | Run 5 |
|---|---|---|
| Student alone: topic lines exact / spurious | 25/27, 0 | 25/27, 1 |
| Student alone: field set exact / spurious | 19/27, 1 | 23/27, 4 |
| Student alone: confrontation found / false | 4/5, 3 | 3/5, **0** |
| Student alone: false empathy, invalid | 0, 0 | 2, 1 |
| Cascade: development exact / spurious | 26/27, 1 (Qwen's) | 25/27, 2 |
| Cascade: test exact / spurious (post hoc) | 67/68, 0 | 66/68, 2 |

Wrong releases in the cascade: "Is this the first time you've taken an overdose?" as current
intent (the confusion Prompt F aimed at, still there), "What are you hoping clozapine will do
for him?" as prior knowledge, and "Has he been seeing things that aren't there?" as the
memory pattern. Run 3 stays.

**After three data rounds (runs 3 to 5):** more data has improved the student's tone
(warm reflections are no longer read as confrontation) and its recall on real lines, but
every later run has released more facts wrongly than run 3, mostly by confusing neighbouring
facts. That looks like the limit of a 0.6B model on this task rather than of the data. The
next experiment, if any, is the same data on Qwen3-1.7B (already downloaded and pinned).

## Qwen3-1.7B on run 5's data (2026-10-14) — level with run 3; not adopted

Same data as run 5 (checked identical by SHA-256), `tools/finetune/lora-1.7b.yaml`: batches of
4 with gradient accumulation over 2, 1,800 batches (about 1.75 epochs), 2.7 hours with every
server running. Validation loss 0.010 at the end (0.6B runs: 0.018–0.020). The step-900
checkpoint was also scored and was much worse on real lines (12 spurious of 27).

| | Run 3 (0.6B) | 1.7B |
|---|---|---|
| Student alone: topic lines exact / spurious | 25/27, 0 | 25/27, 1 |
| Student alone: empathy level / false | 15/20, 0 | **18/20, 0** |
| Student alone: confrontation found / false | 4/5, 3 | **5/5**, 2 |
| Student alone: time per call (no prompt cache) | 0.31 s | 0.82 s |
| Cascade: development exact / spurious | 26/27, 1 (Qwen's) | 25/27, 2 |
| Cascade: test exact / spurious (post hoc) | 67/68, 0 | **68/68, 0** |
| Cascade: test mean interpretation | 360 ms | 379 ms |
| Fidelity (one run): interpretation, leaks, checklist P/R | 96.3%, 0, 0.99/0.975 | 96.3%, 0, 0.99/0.975 |
| Model size | 0.35 GB | 0.95 GB |

For topics, which is all the app uses the student for, the larger model is level with run 3:
one line better on test, one worse on development ("Is this the first time you've taken an
overdose?" as the overdose details, the error runs 4 and 5 also made), equal on fidelity,
for three times the memory. Its tone is the best yet but still marks two warm lines as
confrontational, so tone stays with the classifiers and Qwen. Run 3 stays.

**Conclusion of the student work so far:** run 3 with the cascade's rules is the right
operating point. Further data rounds and a larger model improve tone and recall but not
wrong releases. If tone is wanted from the student, the remaining gap is false
confrontation on specific empathic reflections; the 1.7B model is the closest.

## Run 7: run 6 plus boundary lines (2026-10-20) — not adopted

Worse than run 6 alone (held-out test spurious 141 against 84; tone 14/20 against 20/20) and
in the cascade with the cross-check (92.8% exact, 40 wrong releases, against 93.6% and 31).
Details in docs/STUDENT-CROSS-CHECK-PLAN.md, part B. Run 6 stays.

## Run 6: run 3's recipe plus the catalogue stations (2026-10-17) — adopted 2026-10-20 with the cross-check

Data: run 3's sources plus the 56 catalogue stations' training lines, without the synthetic
interviews (`npm run finetune:export -- --without-synthetic`): 13,926 training rows. Teacher
labels for the 12,474 new lines: Qwen3-4B for 6,707; 5,767 plain questions take their tone
from the runtime rules (no statement and only information-seeking questions: no empathy,
no confrontation), marked `teacher: rules`. `tools/finetune/lora-catalogue.yaml`: 2,000
batches of 8 (about 1.1 epochs), 3.2 hours; validation loss 0.027 at 1,000, 0.029 at 2,000.

| | Run 3 | Run 6 |
|---|---|---|
| Student alone: held-out test (1,097) exact / spurious / invalid | 526 / 24 / 98 | 962 / 84 / 26 |
| Student alone: field set (74) exact / spurious | 20 / 1 | 60 / 9 |
| Student alone: development topics exact / spurious | 25/27, 0 | 24/27, 2 |
| Student alone: empathy level / confrontation found / false | 15/20, 4/5, 3 | **20/20, 4/5, 0** |
| Cascade: catalogue test (1,029) exact | 88.1% | **92.6%** |
| Cascade: catalogue test wrong releases (items) | **43** | 50 (19 fixed, 26 new) |
| Cascade: original test exact / spurious | 67/68, 0 | 67/68, 0 |
| Cascade: development exact / spurious | 26/27, 1 | 26/27, 1 |
| Cascade: catalogue test mean interpretation | 778 ms | 570 ms |

Run 6 sends more lines to the student (337 against 240) and fewer to Qwen, so it is faster
and gets more lines exactly right, but releases more facts wrongly: 37 of its 50 wrong
releases are on the student route (run 3: 9 of 43), mostly a neighbouring fact of the same
station (fear vs guilt, care vs support, attachment vs caregivers). Wrong releases decide
adoption, so run 3 stayed; on 2026-10-20 run 6 was adopted with the cross-check rule, which
removes most of these (docs/STUDENT-CROSS-CHECK-PLAN.md). Run 6's tone is the best of any run (all levels right, no false
confrontation). Report: `artifacts/eval/interpreter-catalogue-student-v6.json`.

## Catalogue stations: classifier training lines (2026-10-17)

The 56 catalogue stations got held-out evaluation data first (d23b766: 1,029 labelled
questions, split test, written by subagents that never saw the question labels), then
topic and tone training lines (2cbd562, drafts). Same cascade, student run 3, Qwen3-4B.
Reports: `artifacts/eval/interpreter-catalogue-{before,after}.json`.

| New stations, 1,029 test questions | Before (no training lines) | After |
|---|---|---|
| Exact match | 81.0% | 88.1% |
| Recall | 78.4% | 84.4% |
| Wrong extra facts | 89 | 43 |
| Median interpretation time | 2.55 s | 0.05 s |
| Routes (classifier / student / Qwen) | 0 / 0 / 1,029 | 585 / 240 / 204 |

- 99 questions fixed, 26 broken (25 on the student route, 1 on the classifier).
- Classifier route: 584 of 585 exact (Qwen got 87.9% of the same questions before); these
  are the questions it is confident on, so the figure is not a general accuracy.
- The before run did not reach the student, so the student's contribution and the training
  lines' are not separated here; the after run is the configuration the app uses.
- Original five stations' test split unchanged: 98.5% exact, 0 wrong extras.
- Smoke test (same 112 questions as before the label pass): 107/112 unlocked, against
  106; median full turn 1.9 s, against about 4.5 s.
- Held-out rapport set (60 lines, shared tone classifier now including 1,324 draft lines):
  93.3% against 95.0% on 2026-10-13, one line net; confrontation recall unchanged (53.8%).
  `artifacts/eval/rapport-cascade-test-3.json`.
- Caveats: training lines are unreviewed drafts; evaluation labels are single-author model
  labels; no clinician has checked either.

## Steps

1. Teacher labels and export; train 0.6B; score on development sets. *(in progress)*
2. Prompt E: synthetic interviews from a frontier LLM; review; retrain.
3. Train 1.7B if 0.6B misses the gates; compare.
4. ~~Serve the student and wire it into the cascade for topics~~ (done 2026-10-14).
5. Tone: retrain with Prompt E interviews; adopt only when it has no false confrontation.
6. Refresh the field set with more of the author's own sessions; retrain periodically.

## Results so far (2026-10-13; development sets only)

Training data: 1,513 lines (authored lines completed by the teacher, plus 74 real-session
turns kept local), 168 for validation. Each step of 8 lines takes about 5 s on the M4, so
300 steps take about 25 minutes.

| Run | Answer format | Topic lines exact / spurious | Empathy level / false | Confrontation found | Time per call |
|---|---|---|---|---|---|
| Untuned Qwen3-0.6B | v1 | 9/27, 7 spurious, 10 invalid | 7/20 | 0/5 | ~1.5 s |
| 1: 250 steps | v1: descriptive topic keys, long field names | **24/27**, 3 | **20/20**, 0 | 0/5 | 0.9 s (bf16) |
| 2: 300 steps, confrontation ×4 | v2: numbered topics, short fields | 21/27, 5 | 14/20, 3 | 0/5 | 0.59 s (bf16), **0.25 s (4-bit)** |
| **3: 600 steps, confrontation ×4** | v3: descriptive topic keys, short fields | **25/27, 0** | 15/20, 0 | 4/5, **3 false** | **0.31 s (4-bit)** |
| Qwen3-4B (gate) | two calls | 25/27, 2 | — | 4/5 (cascade), 0 false | ~2.4 s |

Findings:

- **Speed is solved by merging and 4-bit quantisation** (`tools/finetune/fuse.sh`): 0.25 s
  per call, with accuracy similar to the bf16 adapter. Answer generation dominates the time
  (prompt 511 tokens in 0.2 s; answer 41 tokens in 0.6 s before quantisation), so the answer
  is kept short.
- **Descriptive topic keys beat numbers** for a small model (24 against 21 of 27), as the
  Qwen interpreter's design had already found; run 3 keeps the keys and the short field names.
- **Confrontation was not learned** in 1.4 epochs, even with the rare positive lines
  repeated: the model answered "false" on lines it was trained on while getting their topics
  right (a rare, semantic signal; the averaged loss hides it). Run 3 trains for 2.8 epochs.
  If it still fails, the existing tone classifier can keep the confrontation judgement.
- **Run 3 (2.8 epochs) learned confrontation** (4 of 5 found) and now matches Qwen on topics
  with no spurious selections, in 0.31 s per call. But it marks three specific empathic
  reflections ("Caring for him while working full time sounds like it's left you running on
  empty.") as confrontational, which would cost the trainee rapport. Tone is therefore not
  yet good enough to replace the tone classifier and Qwen's tone call.
- The field set (25 held-out real-session turns) is labelled by Qwen, and most of its lines
  are generic or context-dependent, so agreement there (10 → 17 of 25) is indicative only.
