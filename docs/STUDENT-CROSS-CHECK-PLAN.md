# Plan: a cross-check rule and boundary training lines for the student

Status: 2026-10-20: part A adopted (run 6 with `STUDENT_CROSS_CHECK=all`). Part B done: the
boundary lines are kept because they improve the topic classifiers; run 7 (the student
retrained with them) was worse and is not adopted. Follows run 6 (docs/INTERPRETER-FINETUNE-PLAN.md).

## The problem

Run 6 (run 3's recipe plus the 56 catalogue stations) is faster and more often exactly right
than run 3 in the cascade (catalogue test: 92.6% against 88.1%), but releases more facts
wrongly (50 items against 43), so it was not adopted. The cause:

- Run 3 did not know the catalogue stations, so it often said "none" or gave an invalid
  answer; the cascade then sent the line to Qwen. Its ignorance acted as a safety valve
  (13 of the 26 lines run 6 later got wrong went to Qwen that way).
- Run 6 answers confidently, so it now decides the hardest lines (those the classifier is
  unsure of): 337 against 240. On those its wrong-release rate is 11.0% against 3.7%.
- Its errors are neighbouring facts of the same station (fear vs guilt, care vs support,
  attachment vs caregivers). The training lines teach each fact from its own side; few
  lines teach where two facts divide.
- The safety rules catch a student that says "none" too readily, not one that picks the
  wrong neighbour with confidence.

Two changes target this: a runtime rule that sends disagreements to Qwen (part A), and
training lines that teach the boundaries (part B).

## Measuring honestly

The catalogue test split has now been looked at in detail (the run 6 error list), so any
rule tuned on it would be post hoc. Before any change:

1. **Fresh confirmation set (step 0).** Isolated subagents write a new held-out set for the
   56 catalogue stations by the Prompt B method (fact contents, never the labels), about 10
   questions per station, with split `confirmation`. Committed before any part A or B work.
   It is used once per candidate, at the end.
2. The existing catalogue test split becomes the working set for choosing rule variants;
   results on it are reported as post hoc.
3. Every comparison runs run 3 and the candidate under the same rules.

## Part A: the cross-check rule (runtime)

The topic classifier already computes its best guess when it is not confident
(`Rating.leaning`). New rule in `CascadeInterpreter`, after the student answers an
information question with a topic:

| Classifier leans to | Student says | Now | Proposed |
|---|---|---|---|
| the same fact | that fact | student | student |
| a different fact | a fact | student | **Qwen** |
| none | a fact | student | variant A1: student; variant A2: **Qwen** |

Steps:
1. Log `leaning` in each turn and in evaluation rows (needed to analyse the rule).
2. Implement A1 and A2 behind a setting (`STUDENT_CROSS_CHECK=off|fact|all`), default off
   until evaluated; one function, unit-tested with fixed ratings.
3. On the working set, measure for run 3 and run 6 under each variant: exact, wrong
   releases, share of lines sent to Qwen, mean interpretation time.
4. Choose the variant with the fewest wrong releases whose median turn stays under 2.5 s.

Expected cost: some lines move back to Qwen (about 1.2 s each); the student keeps the lines
where it and the classifier agree.

## Part A results (2026-10-19)

Working set: the catalogue test split (1,029 questions), **post hoc** (its errors were
studied before the rule was written). Reports: `artifacts/eval/interpreter-catalogue-*.json`
and the session scratchpad; the rule is `STUDENT_CROSS_CHECK`.

| Student, rule | Exact | Wrong releases | Mean interpretation | Routes (classifier / student / Qwen) |
|---|---|---|---|---|
| Run 3, off (served) | 88.1% | 43 | 778 ms | 585 / 240 / 204 |
| Run 3, fact | 88.3% | 41 | 805 ms | 585 / 233 / 211 |
| Run 3, all | 88.3% | 40 | 811 ms | 585 / 230 / 214 |
| Run 6, off | 92.6% | 50 | 570 ms | 585 / 337 / 107 |
| Run 6, fact | 93.2% | 38 | 631 ms | 585 / 306 / 138 |
| Run 6, all | 93.0% | **34** | 678 ms | 585 / 288 / 156 |

Original stations' test split: 67/68 exact, no wrong releases, in all six. With `all`, 26
of run 6's 34 wrong releases are Qwen's own (lines handed back), 7 the student's.

**Confirmation set (560 questions, run once each, 2026-10-19):**

| | Exact | Recall | Wrong releases | Mean interpretation |
|---|---|---|---|---|
| Run 3, off (served) | 87.0% | 87.5% | 33 | 886 ms |
| Run 6, all | **93.4%** | **94.8%** | **25** | **713 ms** |

Run 6 with `all` is wrong on 7 lines run 3 got right and right on 15 run 3 got wrong; 19 of
its 25 wrong releases are Qwen's. Reports: `artifacts/eval/confirmation-run{3-off,6-all}.json`.
It meets the adoption rule (fewer wrong releases). Checks before switching (2026-10-20):

- Fidelity scripts, original five stations (163 turns, judge off), against run 3:
  interpretation correct 94.5% -> 97.5%, checklist precision 0.988 -> 1.000, fact status
  98.8% -> 99.4%, no serious errors or unsupported numbers, leak analysis 0/163 flagged;
  median turns faster in every interview kind. One role-player formatting slip (a "facts:"
  tag in a greeting reply, nothing unlocked) counted as a possible leak; the role-player,
  not the interpreter. `artifacts/eval/fidelity-xc-run6-all.json`.
- Smoke test in the app (112 questions): 110/112 unlocked (run 3: 107), median turn 1.85 s.

Adopted: `npm run student:install -- student-0.6b-v6` and `STUDENT_CROSS_CHECK=all` in
`.env`. To revert: install `student-0.6b-v3` and set the rule to off. Tone is unchanged (the student
decides topics only), so the rapport set is not affected.

## Part B: boundary training lines (data)

1. **Find neighbouring facts without looking at test errors.** For each station, rank fact
   pairs by the similarity of their label embeddings (the same embedding model the
   classifiers use) and by confusions on run 6's *validation* split (training data, not
   evaluation). Take the top 2 to 4 pairs per station; script `finetune:pairs`, output
   committed as `data/training/boundaries/pairs.yaml`.
2. **Prompt H (boundary lines).** For each pair: 4 to 6 lines that belong to A but use B's
   obvious words, and the reverse; plus 2 near-miss lines that sound like either but ask
   for something neither holds (topics []). Same rules as Prompt C (trainee knows only
   what it has been told; no copies of labels). Written by isolated subagents with no
   access to `data/evaluation/`. About 56 stations × 3 pairs × 12 lines ≈ 2,000 lines.
3. Saved in `data/training/topics/<id>.boundaries.yaml` so they also train the classifiers;
   near-copy test against all evaluation sets, including the confirmation set.
4. Teacher labels for tone (rules first, Qwen for the rest), as for run 6.

## Part B results (2026-10-20)

- Pairs: `python -m psychiatry_api.finetune.pairs` ranks pairs by label similarity plus 0.04
  per confusion on run 6's validation split; 229 pairs (4-5 per station) in
  `data/training/boundaries/pairs.yaml`.
- Lines: 2,719 (Prompt H, Sonnet subagents without access to evaluation data), 29
  near-copies of evaluation items removed; `data/training/topics/<id>.boundaries.yaml`.
  Teacher tone labels: 1,998 by the runtime rules, 727 by Qwen3-4B.
- Run 7 = run 6's data plus the boundary lines (16,462 rows), batches of 4 with gradient
  accumulation over 2 (`tools/finetune/lora-catalogue-b4.yaml`; batch 8 ran out of GPU
  memory with every server running), 4,000 steps; validation loss 0.018 at 3,000, 0.026 at
  the end.

| Working set (catalogue test, 1,029; post hoc) | Exact | Wrong releases | Mean interpretation |
|---|---|---|---|
| Run 6, all, classifiers without boundary lines | 93.0% | 34 | 678 ms |
| Run 6, all, classifiers with boundary lines | 93.6% | 31 | 693 ms |
| Run 7, all, classifiers with boundary lines | 92.8% | 40 | 674 ms |

Run 7 alone on the held-out test: 942 exact and 141 spurious (run 6: 962 and 84); its tone
also slipped (14/20 empathy levels, 2 false confrontations; run 6: 20/20, 0). The boundary
lines made the student pick a fact more readily rather than draw the boundary better; it
was not taken to the confirmation set. The classifiers, which learn from the same lines,
did improve, so the lines are kept for them.

**Confirmation set, run 6 with `all` and the retrained classifiers (run once):** 93.9% exact,
24 wrong releases, 656 ms (old classifiers: 93.4%, 25, 713 ms). The app's classifiers were
retrained on 2026-10-20 (classifier digest b3c8220297).

## Part C: run 7 and the decision

1. Run 7 = run 6's data plus the boundary lines; same settings (`lora-catalogue.yaml`).
2. Student-alone scores on development, field and the working set (as for run 6).
3. Cascade with the chosen cross-check variant, on the confirmation set, for run 3, run 6
   and run 7.
4. **Adopt** the candidate with the fewest wrong releases on the confirmation set; ties go
   to exact match, then speed. Also required: original stations' test split unchanged (no
   wrong releases), fidelity scripts with no leaks, rapport held-out set not worse.
5. If adopted, `student:install`, record in INTERPRETER-FINETUNE-PLAN.md, update
   NEW-STATION-PROCESS.md (boundary lines become part of adding a station).

## Order and effort

| Step | What | Who | Time |
|---|---|---|---|
| 0 | Confirmation set, committed first | subagents | ~1 h |
| A1-A4 | Leaning logged; rule variants; working-set comparison | code | ~half a day, mostly evaluation runs |
| B1 | Pair finder | code | ~1 h |
| B2-B4 | Prompt H, boundary lines, checks, teacher labels | subagents + Qwen | ~3 h |
| C1 | Train run 7 | MLX | ~3.5 h |
| C2-C4 | Evaluate and decide | scripts | ~1.5 h |

Part A alone may be enough: if run 6 with the cross-check matches run 3's wrong releases
on the confirmation set, it can be adopted without part B. Subagent work is the main spend.

## Tests

- Unit: the cross-check decision table above, including "no classifier for this case".
- Data: boundary files match their cases, at most two topics, no near-copies of any
  evaluation item (existing tests cover the topics folder).
- Evaluation rows carry `leaning`.
