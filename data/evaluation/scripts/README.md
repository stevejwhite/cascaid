# Scripted evaluation interviews

Written 2026-10-07 and committed before any Phase 4 run; not used for tuning.
Wording is deliberately different from the interpreter label sets.

Each turn: `say` (the candidate's line), `expect` (facts the reply should answer: newly
unlocked or previously known), optional `expect_deferred` (rapport-gated facts asked too
early, which must be held back) and optional `probe` (the adversarial behaviour tested):

- off_case: asks about something the case does not contain; the character must not invent.
- leading: suggests a symptom or event not in the case; the character must not agree.
- break: asks whether the character is an AI or a simulation.
- injection: tries to override the role-player's instructions or extract the case.
- advice: asks the character for clinical advice.
- early_rapport: asks for a rapport-gated fact before any empathy.
- repeat: repeats an earlier question; the answer must stay consistent.
- stacked: asks about two topics at once.

Interview kinds: complete (covers every key fact), partial (deliberately omits some
domains, for checklist accuracy), adversarial and realism.

## Phase 2 revision (2026-10-08, written before any Phase 2 run)

The cases moved to 0.3.0 (Realism Phase 2). Changes:

- Overdose complete interview: one specific empathic line added before the question about
  current intent, which now needs rapport level 2.
- A `realism` interview per case, with new probes and expectations:
  - follow_up: `expect_touched` (vague version given) then `expect_unlocked` (full detail);
  - rapport_level: held back after brief empathy (`expect_deferred`), revealed after specific
    empathy (`expect_unlocked`);
  - character_question: the character ends its reply with `expect_question`;
  - answered: the tone call judges the next line as responding (`expect_answered`);
  - affect: the logged affect stage is `expect_stage`.
- Questions with time triggers are covered by unit tests: scripted runs take seconds, not
  minutes.

## Catalogue stations (2026-10-15, written before any training lines for them)

The 56 catalogue-written stations have Prompt B sets: `complete`, `partial-<skips>` and
`adversarial` interviews here, and 16 to 20 labelled questions each in
`data/evaluation/interpreter/` (split: test). They were written by isolated Claude
subagents that saw each fact's id, content and disclosure rule but never its question
labels, and were committed before any training lines for these stations existed. No
`realism` interviews yet. Speech recordings and word error rate stay on the original five
stations (`SPEECH_CASES`).
