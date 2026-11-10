# Realism plan: three phases

Status: Phase 1 complete 2026-10-08 (tag `realism-1`); Phase 2 complete 2026-10-08 (tag
`realism-2`); Phase 3 not started. Follows the Phase 0–4 proof of concept in
[CASC-POC-PLAN.md](CASC-POC-PLAN.md).

## Before Phase 1

Finish the 100 blind ratings (`data/evaluation/ratings/sheet-20261007-1856.csv`), run
`npm run eval:agreement`, and tag the evaluated version (`git tag paper-v1`). The paper's
results describe that version; changing role-play behaviour first would confound them.

## Rules for every phase

- **Disclosure guarantees stay intact.** The role-player never sees a locked fact. New
  behaviours (vague versions, questions, affect stages) are authored in the case, never
  improvised.
- **Each phase ends with an evaluation gate**: three scripted fidelity runs, the leak
  analysis (`npm run eval:leaks`) and the probe review. Early disclosures and inventions
  must be no higher than at `paper-v1`.
- **Each phase ships** tests, updated guides ([ADDING-A-STATION.md](ADDING-A-STATION.md),
  [LLM-STATION-PROMPT.md](LLM-STATION-PROMPT.md)), a git tag and a short results section.
- **Main risk:** more expressive behaviour invites more invented detail. The fidelity gates
  measure exactly that, and the rating sheet can be re-run on the new version.

## Phase 1: Quick wins (about 1 week)

Goal: remove the most noticeable artificiality without changing what the character knows.

| Work | Design | Done when |
|---|---|---|
| Voice per character | Optional persona voice hint (sex, age band, accent). The browser picks the best installed match, falling back to any English voice; a voice picker in the station. Hints added to all five cases. | Each character sounds distinct; female characters no longer use a male voice. |
| No repeated catchphrases | Keep the last three replies; the turn note says not to reuse their closing phrase. Cases may list several deflection lines, used in rotation. | The same closing phrase appears in under 10% of replies. |
| Streaming replies | A streaming endpoint releases the reply sentence by sentence. The output guard checks each sentence before release; a character break stops the reply and substitutes a deflection. Read-aloud starts on the first sentence. | First word shown or spoken 1–2 s sooner; the guard still catches every break in the probes. Measured gain was about 0.5 s; the per-sentence guard is replaced in Phase 2. |
| Exam timing cues | A one-minute warning and a time-up cue, visual and optionally spoken. | Cues at 6:00 and 7:00. |

Gate: as above, plus time to first spoken word.

### Phase 1 results

Three scripted runs of 128 turns each with the registered 4B model and no judge
(`artifacts/eval/fidelity-realism1c-run*.json`, `leaks-realism1c.json`), compared with
the three `paper-v1` runs of the same scripts.

| Measure | `paper-v1` | Phase 1 |
|---|---|---|
| Replies ending with a sentence already said in the interview | 27–34% | 1–4% |
| Leak-screen flags | 0, 1, 0 | 0, 0, 0 |
| Replies with a number not in the case | 0, 0, 0 | 0, 0, 0 |
| Interpretation correct | 92–94% | 92–94% |
| Checklist precision / recall | 0.96–0.98 / 0.93–0.96 | 0.97–0.99 / 0.96–0.97 |
| Early-rapport · repeat · stacked probes (rule-checked) | 2–4/5 · 5/5 · 4–5/5 | 3–4/5 · 5/5 · 5/5 |
| Turn median / p95 | 3.6–3.8 s / 5.0–5.5 s | 3.8–3.9 s / 5.1–5.3 s |
| First sentence shown, median / p95 | whole turn | 3.3–3.4 s / 4.8 s |

Character breaks caught: 2 of 384 replies. In one, the first sentence ("I'm not sure what you
mean.") had already been shown when a later sentence broke character; the reply stopped there.
A live turn through the web proxy streamed three sentences at 3.8, 4.2 and 4.6 s.

What it took, in order:

1. **The turn note was not enough.** The first runs used the note listing recent closing
   sentences ("do not repeat these"). Repeats stayed at 27–32%; the 4B model ignored the note.
   Almost every repeat was a filler line after the real answer ("I just want to go home.").
2. **A deterministic filter fixed repeats.** The guard drops any sentence the character has
   already said in the interview, unless it opens the reply. Repeats fell to 4–5%, but numbers
   not in the case rose to 3, 1 and 3, including a contradiction: an onset of "eighteen months"
   became "two years" on the first turn.
3. **Removing two prompt additions fixed the numbers.** The deflection line's "vary the
   wording" hint and the now-redundant avoid note were removed. Unsupported numbers returned to
   0, and the shorter prompt took about 0.2 s off reply generation.

Targets: repeats under 10% (met); voices per character (met; on-device voices only; a
spoken comparison is Phase 3); timing cues at 6:00 and 7:00 (met, covered by tests);
first word 1–2 s sooner (**not met**, about 0.5 s: interpretation takes about 2.1 s before the
role-player starts, and most replies are one to three sentences). Because of that small gain
and the weaker per-sentence guard, Phase 2 restores the whole-reply guard (below).

The variation between run sets shows that small counts (0–3 per 128 turns) are sensitive to
run-to-run differences in the local model's output. Treat single-run differences of one or
two turns as noise.

## Phase 2: More human character behaviour (about 2–3 weeks)

Goal: characters that change during the interview, without weakening the guarantee.

| Work | Design | Done when |
|---|---|---|
| Graded rapport | The interpreter rates each line's empathy 0–2; a running score builds and slowly decays. Each rapport-gated fact sets the level it needs (1 or 2). Reduces the measured rapport false positives. | Rapport accuracy measured on a new held-out label set, written first; early-rapport probes still pass. |
| Changing affect | Cases describe 2–3 affect stages (guarded, opening up, defensive) triggered by the rapport score or confrontational lines. The current stage goes into the role-player's prompt and the log. | Scripted interviews show the expected shifts; the debrief can show the character's emotional journey. |
| Partial disclosure | Facts may have a vague and a full version: the first question gets the vague answer, a follow-up the detail. Feedback separates "touched on" from "fully elicited". | A new scripted probe confirms vague then full; checklist accuracy re-measured. |
| Characters ask questions | Cases list questions the character asks ("Will he get better?") and when: after a fact is revealed, at a time, or near the end. Most useful in management stations. | Questions appear at the right moments and are logged; feedback shows whether they were answered. |
| Guard the whole reply before release | Replaces Phase 1's sentence-by-sentence guard. The full reply passes the output guard, as at `paper-v1`, and is then shown and spoken sentence by sentence. Keeps the voice, repeat filter and timing cues. See "Why the streaming guard changes" below. | A character break anywhere in a reply replaces the whole reply; the logged reply always equals what was shown; probes re-run. |
| Unsupported-number check | The guard drops a sentence containing a number, duration or age that is not in the known facts or persona (the `unsupported_numbers` screen, applied live). If it drops every sentence, the deflection is used. | Unsupported numbers near zero across three runs, with checklist recall no lower than `paper-v1`, and every drop logged as a flag. |

Gate: as above, plus new probes for rapport levels, vague-to-full disclosure and character
questions. The new fields are documented and added to all five cases.

### Why the streaming guard changes

Phase 1 streamed replies sentence by sentence, with each sentence checked by the output guard
before it was shown. This does not weaken disclosure gating: interpretation and the disclosure
rules finish before the first word, and the role-player never sees a locked fact. It does
weaken the output guard:

- A character break in a later sentence stops the reply, but earlier sentences have already
  been shown. The whole-reply guard replaced the reply with a deflection.
- A break or stage direction that spans two sentences can be missed.
- The turn is logged only when the reply completes. If the browser disconnects mid-reply,
  sentences already shown are not logged.

The gain was small: the first sentence arrived after a median of 3.5 s, against 4.0 s for the
whole turn. Most of the wait is interpretation (≈2.1 s), and most replies are one to three
sentences. The paper's contribution is the disclosure guarantee, so a 0.5 s gain does not
justify a weaker output guard. Making interpretation faster is the better route to a quicker
reply.

Neither guard checks for invented details. In the Phase 1 gate runs, 7 of 384 replies
contained a number that is not in the case, including one contradiction: an onset of
"eighteen months" became "two years". The unsupported-number check is the first live check for
invented details. Its risk is dropping the sentence that answers the question, so its cost to
checklist recall must be measured.

### Phase 2 results

**What was built.** Whole-reply guard with live unsupported-number check; graded rapport
(running level, ×0.8 per turn, +0/1/2 empathy, −1 for confrontation; facts need level 1 or
2); vague-then-full facts; affect stages; character questions with "answered" detection;
debrief sections for touched-on facts, the emotional journey and the character's questions.
All five cases moved to 0.3.0 with these fields.

**Design change: two interpreter calls.** Adding the tone questions to the topic prompt cut
held-out topic exact match from 98.5% to 94.1% and produced 4 spurious selections (0
before). The topic call (`casc-interpret-v1`) is therefore unchanged from `paper-v1`, and
a second call (`casc-tone-v1`) rates the tone. Topic accuracy is identical to `paper-v1`; the
cost is about 1 s per turn.

**Tone call: what it took.** Deterministic rules around the model, each found in testing:

1. Empathy must be quoted from the utterance (plain questions were rated empathic).
2. "Specific" needs at least eight quoted words (stock phrases were rated specific).
3. Empathy quoted from a question does not count, and the tone call sees the trainee's words
   only. With the character's last reply as context, questions such as "How are you coping
   with all of this?" were rated specific empathy and released a level-2 fact early.
4. Confrontation needs quoted words, and a question opening with a question word is never
   confrontational (plain questions about drinking or suicide were flagged).

Held-out rapport labels (60 items, written before the tone call;
`artifacts/eval/rapport-v2-test.json`):

| Measure | `paper-v1` flag | Phase 2 |
|---|---|---|
| Any empathy vs none: accuracy | 93% | 92% |
| False positives / negatives | 1 / 3 | 2 / 3 |
| Level (0/1/2) accuracy | n/a | 82% |
| Brief rated specific / specific rated brief | n/a | 1 of 12 / 5 of 11 |
| Confrontation precision / recall | n/a | 1.0 / 0.54 |

Errors lean the safe way: level-2 facts are hard to unlock by accident, but specific empathy
is often under-credited and half of confrontational lines are missed.

**Gate** (`fidelity-realism2-run*.json`; 163 turns per run: the 128 `paper-v1` turns, one
added empathic line, and 34 new realism-probe turns). The first attempt at run 3 stopped at
turn 161 when the local model server went down and was repeated in full; runs 1 and 3 gave
identical results.

| Measure (128 original turns unless stated) | Phase 1 | Phase 2 runs 1, 2, 3 |
|---|---|---|
| Leak-screen flags (all turns) | 0, 0, 0 | 1, 0, 1 |
| Replies with a number not in the case (all turns) | 0, 0, 0 | 0, 0, 0 |
| Repeated closing sentence (all turns) | 1–4% | 2.5%, 0.6%, 2.5% |
| Interpretation correct | 92–94% | 93.8%, 93.0%, 93.8% |
| Checklist precision / recall | 0.97–0.99 / 0.96–0.97 | 0.985 / 0.941 (all three) |
| Early-rapport probes | 3–4/5 | 4/5, 4/5, 4/5 |
| Turn median / p95 | 3.8–3.9 s / 5.1–5.3 s | 4.9 s / 6.4–6.7 s |
| First sentence shown (median) | 3.3–3.4 s | 4.9 s (whole reply guarded first) |

The leak flag (runs 1 and 3, the same turn) is not a role-player leak: the topic call read "Usually every week at
first…" as a question about Daniel's fear of needles and released that fact. All four
checklist misses are topic-call misses ("Who or what in your life matters to you?" selected
no topic); rapport was sufficient each time. The topic call is unchanged, but it sees the
character's previous reply, which Phase 2 changes.

New probes (runs 1, 2, 3):

| Probe | Passed | Failures and cause |
|---|---|---|
| Vague then full (`follow_up`) | 8/10, 10/10, 8/10 | Runs 1 and 3: "his last medication" mapped to the wrong fact (topic call) |
| Rapport level | 3/4, 3/4, 3/4 | Carer strain released one turn early: the topic call read an empathic statement as asking about coping |
| Character question asked | 2/3, 2/3, 2/3 | "What do you make of your sister's worries?" selected no topic, so the fact and its question never came |
| Question answered | 2/3, 2/3, 2/3 | Follows from the line above (no question was pending) |
| Affect stage | 4/6, 4/6, 4/6 | Two confrontational lines not flagged (tone recall) |

Every failure traces to a classifier miss (topic or tone), none to the new deterministic
rules. Release of a fact still happens only through the rules; no role-player leak was found.

**Targets.** Rapport accuracy measured on a held-out set written first (met; binary accuracy
level with `paper-v1`, not better). Early-rapport probes still pass (4/5, up from 3–4/5). Vague
then full confirmed (26/30). Questions and affect shifts appear and are logged (met where the
classifiers fire). Checklist recall fell from 0.96–0.97 to 0.94: four topic-call misses.

**Costs.** Turns are about 1.1 s slower (the tone call), and nothing is shown until the whole
reply has been guarded, so the first sentence now appears at 4.9 s rather than 3.3 s.

## Phase 3: Spoken realism

> Superseded in part (2026-10-13): neural voices, end-of-speech detection and interruption
> are now delivered by the avatar prototype in [AVATAR-PLAN.md](AVATAR-PLAN.md). Linked
> stations remain here. (about 3–4 weeks)

Goal: a spoken exchange that feels like talking rather than taking turns on a radio.

| Work | Design | Done when |
|---|---|---|
| Local neural voices | A pinned, checksum-verified text-to-speech model (Kokoro or Piper class) as a local server, like Whisper. Voice per persona; pace and tone follow the Phase 2 affect stage. | Measured: time to first audio, memory with all models loaded, and a blind naturalness comparison against system voices. |
| End-of-speech detection | Browser voice-activity detection replaces click-to-talk, which stays as a fallback for noisy rooms. | Measured on the real-voice recordings: missed and false cut-offs. |
| Interrupting the character | Starting to speak stops the character's audio and cancels its reply; the log records the interruption. | Interruptions handled within 300 ms. |
| Linked stations | Two-part stations (history, then explaining to a relative) carrying facts from part one into part two; one new linked case. | Runs end to end; feedback covers both parts. |

Gate: the full evaluation including real-voice recordings, and a re-measured memory budget
on the 16 GB Mac.

**Avatar:** out of scope. Decide after Phase 3 whether voice realism is enough.

Overall: about 6–8 weeks; Phase 1 alone fixes most of what testing showed.
