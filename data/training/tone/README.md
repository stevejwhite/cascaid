# Tone-classifier training data

Drafted by **GPT-6 (Codex)** on **12 October 2026**; revised against the updated Prompt D quality rules on **13 October 2026**. A more specific model snapshot identifier was not available.

All five files were **reviewed by Steve J White on 2026-10-13** (`status: reviewed`), using case version **0.3.0**; the headers now say 0.4.0, which changed presentation only (character, voice, expression, hesitations), not facts, topics or disclosure rules. These are original synthetic training examples, not evaluation data. They have not received clinical review and do not establish clinical validity. Creating these files does not train or deploy a classifier.

## Addition on 2026-10-13: impatient lines

Fifteen lines (three per case, style `impatient`, confrontational, empathy 0) were added by
Claude (Opus 5.5) after the held-out evaluation of the classifier cascade missed an
impatient command that the Qwen interpreter caught. They cover impatience and pressure to
answer, which the drafted confrontational lines did not. Because the gap was found on a
held-out line, the held-out confrontation result measured after this addition is not an
unbiased estimate; the clean result is the one measured before it. The counts below are as
drafted, before this addition (83 lines per case now, 415 in total).

## Counts by case and label

The four label columns below are mutually exclusive. “Neutral” means empathy 0 and not confrontational; all confrontational lines also have empathy 0. Thus the raw empathy-0 count is 52 per case, or 260 overall.

| Case | Total | Neutral | Empathy 1 | Empathy 2 | Confrontational |
| --- | ---: | ---: | ---: | ---: | ---: |
| alcohol-history | 80 | 40 | 14 | 14 | 12 |
| clozapine-explanation-relative | 80 | 40 | 14 | 14 | 12 |
| elevated-mood-history | 80 | 40 | 14 | 14 | 12 |
| memory-collateral-history | 80 | 40 | 14 | 14 | 12 |
| overdose-risk-assessment | 80 | 40 | 14 | 14 | 12 |
| **Total** | **400** | **200** | **70** | **70** | **60** |

## Counts by style

Each case has the same style distribution.

| Style | Per case | All five cases |
| --- | ---: | ---: |
| `plain_question` | 15 | 75 |
| `polite_question` | 6 | 30 |
| `greeting` | 3 | 15 |
| `introduction` | 2 | 10 |
| `summary` | 2 | 10 |
| `explanation` | 2 | 10 |
| `check_understanding` | 2 | 10 |
| `acknowledgement` | 8 | 40 |
| `brief_empathy` | 8 | 40 |
| `brief_empathy_question` | 6 | 30 |
| `specific_empathy` | 9 | 45 |
| `specific_empathy_question` | 5 | 25 |
| `confront_statement` | 4 | 20 |
| `confront_why` | 2 | 10 |
| `confront_tag` | 2 | 10 |
| `confront_rhetorical` | 1 | 5 |
| `dismissive` | 3 | 15 |
| **Total** | **80** | **400** |

Each file includes 11 lower-case spoken-style lines (55 overall), approximately one in seven. Empathic statements retain their terminating full stop before any question.

Each case has **10 specific-empathy lines with a previous exchange and 4 without one** (50 with and 20 without overall). Each retained `previous.character` is copied exactly from a fact in that case. Lines without an exchange use only the opening statement or a volunteered fact; their grounding is listed below. Specific-empathy statements contain at least eight words. Questions about sensitive subjects remain neutral unless a separate empathic statement precedes them.

## Revision for the refined quality rules

Rewrote all **60 confrontational lines**, **40 acknowledgements** and **70 specific-empathy lines**. The 400-item total, item order, labels, styles, case versions and YAML field format are unchanged. Other utterances are unchanged.

- Confrontation now illustrates realistic trainee mistakes: pressure to agree, lecturing, impatience, disbelief, minimisation and premature reassurance. No revised line was judged openly hostile or insulting during the drafting review, within the maximum of three per case. They remain deliberately poor responses, labelled empathy 0 and confrontational.
- Acknowledgements are short conversational responses, sometimes followed by a brief question, instead of formal notes or transitions.
- Specific empathy uses varied forms: recognising a concern, validating a perspective, acknowledging effort and reflecting a disclosed feeling. The repeated “situation sounds adjective” construction no longer dominates.
- Items **59–62** in every file have no `previous` exchange. The other ten specific-empathy items retain exact case-fact context. Eleven spoken-style lines per case are preserved.

### Grounding for specific empathy without a previous exchange

Positions are one-based within `items`.

| Case | Items | Already disclosed source |
| --- | --- | --- |
| alcohol-history | 59–62 | Opening: GP referral after liver tests; Chris does not think the drinking is that bad. |
| clozapine-explanation-relative | 59, 61, 62 | Opening: Maria wants to understand what clozapine means for Daniel before he starts. |
| clozapine-explanation-relative | 60 | Volunteered `treatment-history`: two tablets tried; voices still present most days. |
| elevated-mood-history | 59, 62 | Volunteered `new-business`: plans to restore vintage bikes and expects the business to be big. |
| elevated-mood-history | 60, 61 | Opening: feeling great, energetic and full of plans; sister wanted the meeting. |
| memory-collateral-history | 59–62 | Opening: worsening memory and Helen's concern about her dad being safe living alone. |
| overdose-risk-assessment | 59–61 | Opening: Jordan says they feel fine and want to go home. |
| overdose-risk-assessment | 62 | Volunteered `medically-fit`: blood tests okay; opening: wants to go home. |

## Label boundaries and review

Brief empathy expresses generic sympathy; specific empathy reflects the person's disclosed circumstances. Politeness, greetings, summaries and neutral acknowledgements are empathy 0. Confrontational examples deliberately illustrate challenging, blaming or dismissive language; they are negative training examples. No line is both empathic and confrontational. The labelled words are exact substrings of their utterance.

Contrasting examples cover the same subject with different tone. The following one-based item positions help reviewers locate those boundaries:

| Case | Polite question / brief empathy with question | Plain question / confrontation | Brief / specific empathy |
| --- | --- | --- | --- |
| alcohol-history | 18 / 49 | 2 / 76 | 42 / 57 |
| clozapine-explanation-relative | 16 / 49 | 1 / 78 | 46 / 55 |
| elevated-mood-history | 16 / 52 | 1 / 70 | 45 / 58 |
| memory-collateral-history | 16 / 49 | 1 / 78 | 50 / 56 |
| overdose-risk-assessment | 17 / 49 | 4 / 74 | 43 / 56 |

No unresolved label ambiguities were identified during drafting. Human review remains outstanding, particularly for naturalness and whether each specific-empathy statement accurately reflects the disclosed situation.

## Validation

The required training-data tests passed after this revision: **3 passed**, including label consistency and separation from unseen evaluation material. The required count check also passed. No unseen evaluation examples or test source were opened. During the original draft, four candidates had been rejected for similarity and were rewritten; the quality-rule revision did not introduce further similarity failures.

Run from the repository root:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTEST_ADDOPTS='--tb=line -p no:cacheprovider' uv run --project services/api --locked pytest -q services/api/tests/test_training_data.py
```

The environment settings suppress bytecode/cache writes and keep failure reporting concise; they do not change test selection.

The required count check passed for all five cases:

```sh
uv run --project services/api --locked python - <<'PY'
import collections, glob, yaml
for path in sorted(glob.glob("data/training/tone/*.yaml")):
    items = yaml.safe_load(open(path))["items"]
    labels = collections.Counter(
        ("confrontational" if i["confrontational"] else f"empathy {i['empathy']}")
        for i in items)
    print(path, len(items), dict(labels))
PY
```

Additional checks covered schema fields, case versions, style distributions, quoted substrings, empathy punctuation and word counts, exact grounding of previous replies, opening repetition (including resolving two repeated openings found during this revision), and punctuation-only or single-word near-duplicates across the 400 lines. These checks passed; they are not a substitute for human review.

For this task, no excluded files were opened, searched or grepped. The required test was executed without reading its source or held-out examples. Writes were confined to `data/training/tone/`. No commit was made.

## Catalogue stations (2026-10-15 to 2026-10-17)

24 lines per station for the 56 catalogue stations (1,324 after overlap removal): 12
empathy 0, 4 brief, 4 specific, 4 confrontational, scaled down from Prompt D's 80 so the
shared tone classifier is not dominated by unreviewed lines. Drafted by Claude subagents
without access to `data/evaluation/`; **status: draft, not reviewed.**
