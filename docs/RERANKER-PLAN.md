# Plan: a reranker to decide topics

Status: stages 0 and 1 done (2026-10-21). Zero-shot, the reranker is worse than the served
student; stage 2 is skipped. Stage 3 (fine-tuning) is the remaining option, not started.

## Why

Deciding which fact a trainee's line asks about is a matching task: score the line
against each of the station's facts and take the best, or none. The student (a 0.6B
generative model fine-tuned to write a JSON label) does it indirectly, and four rounds of
extra data (runs 4, 5, 7 and a 1.7B model) never reduced its wrong releases; the runtime
rules around it did. A **reranker** (cross-encoder) is built for exactly this: it reads a
query and one candidate together and returns a relevance score. That gives what the student
lacks:

- a score per fact, so "none" is a threshold and doubt is visible (a small margin between
  the top two facts), not a guess;
- the line and the fact's description read together, which is where neighbouring facts
  (fear vs guilt) are told apart;
- one model for every station, with the station's facts given at run time.

## Candidate

**Qwen3-Reranker-0.6B** (GGUF), the same family and size as the embedding model already
served. llama.cpp (our pinned build) serves rerankers with `--rerank --pooling rank`.
Before download: confirm the licence (Qwen3 models are Apache-2.0; check the model card),
then pin repository, revision and file SHA-256 in `config/model-register.json` with a licence
record, as for the other models. If its quality or llama.cpp support disappoints,
BGE-reranker-v2-m3 (Apache-2.0) is the alternative.

Memory: about 0.6 to 1 GB more on a 16 GB Mac. Training runs (stage 3) need the batch-4
settings, as for run 7.

## How it decides

For each line, the reranker scores the line (with the previous exchange for follow-ups)
against each fact's **description**. Two description variants are compared in stage 1:

- D1: the fact's question labels (`asked_about`), as the Qwen interpreter sees them;
- D2: the labels plus the fact's content (a richer match; the reranker is internal and its
  scores are never shown to the role-player, so no fact is revealed by it).

Decision rule (parameters chosen on the working set):

| Top score | Margin to second fact | Decision |
|---|---|---|
| below T | any | none |
| at least T | at least M | the top fact |
| at least T | below M | Qwen decides (the reranker is unsure between neighbours) |

The existing rules stay: compound lines and statements or leading questions given a topic
still go to Qwen. Two-topic lines (stacked questions) are left to Qwen in this version.

## Measuring honestly

- Working set: the catalogue test split (1,029) plus the original stations' test split
  (68): used to choose D1/D2, T and M; reported as **post hoc**.
- Confirmation set (560): once per final candidate.
- The confirmation set has now been used for three candidates. After this plan, write a
  fresh one (Prompt B2 again) before any further round, so it stays a real held-out test.
- Comparison throughout: the served configuration (run 6, `STUDENT_CROSS_CHECK=all`,
  classifiers with boundary lines): confirmation 93.9% exact, 24 wrong releases, 656 ms.

## Stages

**Stage 0: plumbing (code, tests).**
- `npm run models:install` support for a reranker entry; `models:start` serves it on
  127.0.0.1:8185 with `--rerank`; loopback only, like the others.
- `psychiatry_api.models.reranker`: adapter (POST /v1/rerank), with a fake for tests.
- `RerankerTopics` in `roleplay/classify.py`, alongside `StudentTopics`, behind a setting
  `TOPIC_DECIDER=student|reranker` (default student); calls logged with model, revision,
  scores and time.
- Unit tests: decision table, thresholds, fall-back to Qwen on failure.

**Stage 1: zero-shot, offline (no cascade).**
- A script scores every working-set line against every fact of its station and stores the
  scores (about 1,100 lines × about 11 facts; minutes).
- Choose D1 or D2, then T and M, by wrong releases first, then exact match.
- Report: alone (as a classifier) against run 6 alone.

**Stage 2: zero-shot in the cascade.**
- Placement A: reranker in the student's place (classifiers, then reranker, then Qwen).
- Placement B: reranker instead of both the classifiers and the student (one model for all
  stations; a new station needs no classifier training).
- Working set for both, with latency; the better one goes to the confirmation set if it
  beats the served configuration on the working set.

**Stage 3: fine-tune (only if stage 2 is promising but not decisive).**
- Pairs from the authored training lines (never evaluation data): each line with its fact
  (positive), its boundary neighbour (hard negative, from `data/training/boundaries/pairs.yaml`)
  and two other facts of the station (negatives); no-topic lines against every fact
  (negatives). About 60,000 pairs.
- LoRA with MLX (the reranker is a Qwen3-0.6B: it scores "yes" against "no" as the next
  token, so the student's tooling applies), then fuse and convert to GGUF for llama.cpp,
  or serve from MLX if conversion fails.
- Same evaluation as stage 2.

## Stage 0 and 1 results (2026-10-21)

**Serving.** Qwen publishes no GGUF of the reranker, so the official weights
(Qwen/Qwen3-Reranker-0.6B@e61197ed, Apache-2.0, checked against Hugging Face's SHA-256
records) are served with MLX (`npm run reranker:start`, 127.0.0.1:8185). Scoring a station's
10 to 14 facts in one batch took about 410 ms; sharing the instruction and line across the
batch (one prefix pass, its keys and values repeated; identical tokens, bf16 differences up
to 0.03) halves that: median 201 ms with labels, 315 ms with labels and content. An 8-bit
copy was not faster (prompt reading is compute-bound) and was dropped.

**Working set (catalogue and original test splits, 1,097 lines; post hoc).** Tool:
`python -m psychiatry_api.evaluation.rerank score|analyse`; scores and the full grid in
`artifacts/eval/reranker/`. The cascade is simulated from recorded runs: classifier
decisions from the served configuration's run, then the reranker under the cascade's rules,
then Qwen's decision from a run where Qwen decided every line (the two runs agree on all
144 lines Qwen decided in both).

| | Exact | Wrong releases |
|---|---|---|
| Served (run 6, `all`, classifiers with boundary lines) | **1,030** | **31** |
| Reranker in the student's place, labels and content, best T/M | 983 to 1,002 | 38 to 48 |
| Reranker in the student's place, labels only, best T/M | 987 to 999 | 41 to 50 |
| Run 6 student alone | 962 | 84 |
| Reranker alone, labels and content (T 0.1 to 0.9) | 662 to 818 | 31 to 160 |

Untrained, the reranker matches surface words (for "What worries you most about her being
told?" it ranks "sharing the diagnosis" first) and trades exact matches against wrong
releases without reaching the student's level at any setting. Including the fact's content
helps slightly. Placement B (no classifiers) would rest on the reranker alone, which is far
below the cascade, so stage 2 is skipped.

**Decision.** Stage 3 is the only route left: fine-tune the reranker on the authored and
boundary lines with neighbouring facts as hard negatives. A fine-tuned cross-encoder is
where such models usually gain most, but it is a day's work with no guarantee; the served
configuration stays meanwhile.

## Adoption rule

As before: fewer wrong releases on the confirmation set than the served configuration;
then exact match, then latency (median turn under 2.5 s). Also: original stations
unchanged, fidelity scripts with no leaks, app smoke test. Rapport is unaffected (topics
only).

## Order and effort

| Stage | What | Time |
|---|---|---|
| 0 | Model pinned, served; adapter, setting, tests | half a day |
| 1 | Offline scoring and thresholds | 1 to 2 hours |
| 2 | Two placements in the cascade; confirmation run | 2 hours, mostly evaluation |
| 3 | Fine-tune (if needed) | a day, including about 4 hours' training |

No subagents are needed for stages 0 to 2.

## Risks

- The zero-shot reranker may be weak on short colloquial lines ("and at night?"); the
  previous exchange is part of the query for that reason.
- Calibration differs between stations; a single T and M may not suit all. If so, try a
  per-station T from training lines (never evaluation data).
- llama.cpp's reranking path for Qwen3-Reranker must be checked on this build (stage 0);
  if it is unsupported, serve it from MLX.
