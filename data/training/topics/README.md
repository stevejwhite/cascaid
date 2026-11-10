# Topic-classifier training phrasings

Drafted and revised by **GPT-6 (Codex)** on **12 October 2026**. GPT-6 is the model
version identified in this session; no more specific snapshot was provided.

**Reviewed by Steve J White on 2026-10-12 (`status: reviewed`). Use these files only for
training, never for evaluation or as a held-out test set.** These fictional cases and labels
are not clinically validated.

## Revision to Prompt C

- Rewrote standalone questions around what the trainee is allowed to know: the candidate
  instructions, opening statement, volunteered facts and general clinical knowledge.
  Hidden quantities, relatives, places and events are no longer supplied in questions.
- Follow-ups have explicit prior exchanges. Every `previous.character` is copied exactly
  from its associated case fact; the preceding interviewer line does not assume its
  answer. Specific disclosed details may be used in the follow-up itself.
- Restored everyday words in roughly half of each fact's 15 lines, with natural alternate
  wording in the remainder. Removed the former quarter-overlap limit and its forced
  synonyms. There is exactly one plainly worded `clinical` line per fact.
- Varied openings within each fact and simplified formal wording such as “venepuncture”,
  “ethanol”, “denial” and “abstinence”. No two lines within a fact share the same first
  two word tokens; no within-file pair differs only by punctuation or one word.
- Replaced all 20 `off_case` and 20 `near_miss` lines. These are plausible clinical
  questions about separate unsupported topics, not trivia or requests for missing
  details of an existing fact. Examples include family history of suicide versus
  personal protective relationships, and deliberate overdose versus remembering doses.
- Revised summaries and empathy where they previously assumed undisclosed information.
  Empty-topic statements still follow the interpreter's rules.

All original item counts, topic assignments, style counts, case versions and YAML fields
are preserved. Every one of the 55 facts, including volunteered facts, has 15 single-topic
lines across ten styles. Each case has four stacked lines and 30 no-topic lines.

## Overlap removal (2026-10-12)

After the revision, 24 lines were removed because they were near-copies (difflib ratio at
least 0.75 on normalised words) of evaluation items the drafting model was not allowed to
see: the interpreter label sets, scripted interviews and rapport label sets. Three were
identical to evaluation questions. Natural questions converge, so this is expected; the
test `services/api/tests/test_training_data.py` now enforces it for any future additions.

| Case | Removed | Items now |
| --- | ---: | ---: |
| `alcohol-history` | 6 | 208 |
| `clozapine-explanation-relative` | 5 | 164 |
| `elevated-mood-history` | 2 | 182 |
| `memory-collateral-history` | 5 | 194 |
| `overdose-risk-assessment` | 6 | 223 |
| **Total** | **24** | **971** |

Every fact keeps 13 to 15 single-topic lines. The tables below give the counts as drafted,
before this removal.

## Conversational lines (draft)

`*.conversational.yaml` (2026-10-13, 196 lines) add generic openers, introductions and
transitions (no topic) and questions addressed by name or with a preamble, after logged
sessions showed most such lines fell to Qwen. They were drafted by Claude and are marked
`status: draft`: **not yet reviewed by a person**. See docs/AVATAR-PLAN.md, "Speed
improvements".

## Counts per case

Drafted against case version 0.3.0. The file headers now say 0.4.0 (2026-10-13), which changed
presentation only (character, voice, expression, hesitations); facts, topic labels and
disclosure rules are unchanged, so these lines still apply.

| Case | Version | Facts | Single-topic | Stacked | No-topic | Total |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `alcohol-history` | 0.3.0 | 12 | 180 | 4 | 30 | 214 |
| `clozapine-explanation-relative` | 0.3.0 | 9 | 135 | 4 | 30 | 169 |
| `elevated-mood-history` | 0.3.0 | 10 | 150 | 4 | 30 | 184 |
| `memory-collateral-history` | 0.3.0 | 11 | 165 | 4 | 30 | 199 |
| `overdose-risk-assessment` | 0.3.0 | 13 | 195 | 4 | 30 | 229 |
| **Total** | | **55** | **825** | **20** | **150** | **995** |

## Counts per style

| Style | Alcohol | Clozapine relative | Elevated mood | Memory collateral | Overdose | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `open` | 24 | 18 | 20 | 22 | 26 | 110 |
| `closed` | 24 | 18 | 20 | 22 | 26 | 110 |
| `colloquial` | 24 | 18 | 20 | 22 | 26 | 110 |
| `clinical` | 12 | 9 | 10 | 11 | 13 | 55 |
| `indirect` | 12 | 9 | 10 | 11 | 13 | 55 |
| `empathy_then_question` | 12 | 9 | 10 | 11 | 13 | 55 |
| `spoken` | 24 | 18 | 20 | 22 | 26 | 110 |
| `brief` | 12 | 9 | 10 | 11 | 13 | 55 |
| `follow_up` | 24 | 18 | 20 | 22 | 26 | 110 |
| `leading` | 12 | 9 | 10 | 11 | 13 | 55 |
| `stacked` | 4 | 4 | 4 | 4 | 4 | 20 |
| `greeting` | 3 | 3 | 3 | 3 | 3 | 15 |
| `introduction` | 3 | 3 | 3 | 3 | 3 | 15 |
| `empathy` | 4 | 4 | 4 | 4 | 4 | 20 |
| `summary` | 4 | 4 | 4 | 4 | 4 | 20 |
| `explanation` | 4 | 4 | 4 | 4 | 4 | 20 |
| `check_understanding` | 4 | 4 | 4 | 4 | 4 | 20 |
| `off_case` | 4 | 4 | 4 | 4 | 4 | 20 |
| `near_miss` | 4 | 4 | 4 | 4 | 4 | 20 |

## Extended self-check review

The revised Prompt C self-check passed its structural assertions, with no short fact
counts and exactly 30 no-topic items per case. Every emitted `CHECK` line was reread.
The check is a lexical warning, not proof of leakage: it also flags ordinary words such
as “hours”, “without” and “there”. It intentionally skips follow-ups and no-topic lines,
and only checks the first topic of a stacked item. Those areas were reviewed separately.

Earlier wording that presumed shift work, a heavy quantity, or a particular interruption
trigger was revised. The final flags below are retained because they are general clinical
questions, allowed general leading guesses, facts already in the briefing, or ordinary
grammatical words—not hidden answers. Item numbers are one-based positions in each YAML
`items` list, so every retained warning can be located individually.

| Case | Final CHECK lines reviewed |
| --- | ---: |
| `alcohol-history` | 20 |
| `clozapine-explanation-relative` | 9 |
| `elevated-mood-history` | 33 |
| `memory-collateral-history` | 28 |
| `overdose-risk-assessment` | 17 |
| **Total** | **107** |

<details>
<summary>Decisions covering every retained CHECK line</summary>

| Case / topic | Item positions | Matched words | Decision: retain because… |
| --- | --- | --- | --- |
| `alcohol-history` / `quantity` | 3, 11 | through | Ordinary phrasing about total intake; no drink type, bottle size or amount supplied. |
| `alcohol-history` / `withdrawal` | 32, 36, 39, 41 | without | Conditional questions about going without alcohol, not an assertion that symptoms occurred. |
| `alcohol-history` / `tolerance` | 52, 56 | before | General comparison over time; no amount or direction is supplied as a fact. |
| `alcohol-history` / `duration` | 63, 71 | years | Asks about the timescale without supplying the hidden duration or divorce. |
| `alcohol-history` / `loss-of-control` | 76, 77, 82 | tried | Asks whether reduction has been tried; gives no number of attempts or days. |
| `alcohol-history` / `consequences` | 101 | licence | Driving-licence consequences are a general alcohol-history question; no loss of licence is asserted. |
| `alcohol-history` / `mood` | 109 | whether | The matched word is grammatical; no mood answer is supplied. |
| `alcohol-history` / `risk` | 124, 132 | ending | Ordinary wording for a suicide-risk question; no answer is assumed. |
| `alcohol-history` / `other-substances` | 137, 146 | smoke | Asks about smoking, with no brand, amount or claimed smoking status. |
| `alcohol-history` / `withdrawal + loss-of-control` | 182 | without | Two general questions; neither supplies a withdrawal event or a reduction outcome. |
| `clozapine-explanation-relative` / `prior-knowledge` | 28 | people | Asks about information received without identifying the hidden friend or their warning. |
| `clozapine-explanation-relative` / `smoking` | 61, 66, 67, 71 | about, smokes | Generic topic and grammatical words; conditional amount questions give no cigarette count. |
| `clozapine-explanation-relative` / `adherence` | 92, 99 | forget, sometimes | General missed-dose question or general leading guess; no reminder routine or person is supplied. |
| `clozapine-explanation-relative` / `hopes` | 123, 134 | getting | Getting better is a general treatment aim, not the hidden hope of returning to college. |
| `elevated-mood-history` / `sleep-reduced` | 2, 5, 11 | about, hours, tired | Hours and tiredness are general sleep questions; no three-hour answer is supplied. |
| `elevated-mood-history` / `mood-onset` | 21, 22, 24, 29 | people, unusually, upbeat | Generic question/empathy wording; feeling great is in the opening. No hidden interruption event is asserted. |
| `elevated-mood-history` / `function-work-spending` | 32, 36 | afford, spent | General spending and affordability questions, without a price, purchase or missed-shift count. |
| `elevated-mood-history` / `risk-driving` | 47, 49, 52, 53, 54, 57 | about, harming, haven, usual | General risk questions or a general leading guess; no journey, speed or denial is supplied. |
| `elevated-mood-history` / `support-sister` | 62, 64 | offered | Asks about any offers of support; does not identify who offered or for how long. |
| `elevated-mood-history` / `substances` | 76, 79, 89 | medicines, prescribed, recreational | General categories of substances, without coffee quantities or claimed use/abstinence. |
| `elevated-mood-history` / `past-low-period` | 95, 96, 97, 104 | feeling, period | General past-mood questions; no date or duration of the hidden episode is supplied. |
| `elevated-mood-history` / `family-and-physical` | 106, 107, 108, 109, 111, 113, 114, 117, 119 | illness, problems, similar | General health/family-history questions or a general leading guess; no relative or diagnosis is supplied. |
| `memory-collateral-history` / `onset` | 3, 11, 12, 13, 14 | about, change, there | General time-course or grammatical words; no eighteen-month duration is supplied. |
| `memory-collateral-history` / `memory-pattern` | 17, 23 | questions | Repeated questions are a general memory symptom to ask about; no specific conversation or naval memory is supplied. |
| `memory-collateral-history` / `getting-lost` | 33 | after | After is grammatical; asks about finding the way without naming a destination or police involvement. |
| `memory-collateral-history` / `daily-function` | 46, 47, 50, 52, 53, 58 | meals, paying, proper | Meals and payments are general daily-function questions, not claims about arrears or electricity. |
| `memory-collateral-history` / `cooker-safety` | 66 | found | Generic appliance-safety question; no observed incident or number is asserted. |
| `memory-collateral-history` / `mood-behaviour` | 77, 88, 89 | irritable, there, things | Generic symptom questions, including absence/presence; no particular incident is asserted. |
| `memory-collateral-history` / `physical-health` | 101 | takes | Routine medication question; no named medicine, diagnosis or answer is supplied. |
| `memory-collateral-history` / `alcohol` | 111, 119 | glass, years | General questions about a drink and current/former tobacco use; no whisky or date is supplied. |
| `memory-collateral-history` / `his-view` | 138, 139 | bring, could | Ordinary wording asking about his response; no permission or angry reaction is supplied. |
| `memory-collateral-history` / `carer-strain` | 151, 156, 162, 164 | about, after | General enquiry about the daughter’s experience; no visit schedule, exhaustion or guilt is supplied. |
| `memory-collateral-history` / `daily-function + cooker-safety` | 167 | meals | General cooking and appliance-safety questions; no payment event or number of incidents is supplied. |
| `overdose-risk-assessment` / `overdose-details` | 26 | about | About is grammatical; the overdose is in the candidate instructions, but its hour is not supplied. |
| `overdose-risk-assessment` / `planning` | 32 | planned | Asks whether the act was planned, without naming a purchase, shop or preparation interval. |
| `overdose-risk-assessment` / `precautions` | 54, 58 | nobody, until | General questions/leading guesses about avoiding interruption; no flatmate or weekend arrangement is supplied. |
| `overdose-risk-assessment` / `note` | 71 | wrote | Asks about any note, without a recipient, location or assertion that one exists. |
| `overdose-risk-assessment` / `discovery` | 82 | called | Asks who called; does not supply the flatmate or emergency transport. |
| `overdose-risk-assessment` / `current-intent` | 94, 99 | again | Again refers to the known overdose; questions/leading guesses do not supply a current-intent answer. |
| `overdose-risk-assessment` / `mood` | 131 | about, enjoyable | Generic question about mood and pleasure; no low-mood duration is supplied. |
| `overdose-risk-assessment` / `alcohol` | 161 | about | About is grammatical; no wine, bottle amount or relationship event is supplied. |
| `overdose-risk-assessment` / `access-to-means` | 167, 171, 172, 174, 177, 178, 179 | there | There is grammatical; asks about availability without naming the bathroom cabinet or asserting a supply. |

</details>

The remaining warnings are not unresolved label choices. No uncertain alternative-topic
assignment was identified in this drafting pass. Human label review is still outstanding,
particularly for the boundaries of the no-topic clinical questions. No automated check
establishes clinical validity, naturalness or correct semantic labels.

## Reproduce the requested self-check

Run from the repository root. The code below is the revised Prompt C check. Disabling
bytecode writing keeps validation from creating Python cache files in the source tree.

```sh
PYTHONDONTWRITEBYTECODE=1 uv run --project services/api --locked python - <<'PY'
import collections, glob, re, yaml
from psychiatry_api.cases import load_cases
cases = {c.id: c for c in load_cases()}
for path in sorted(glob.glob("data/training/topics/*.yaml")):
    data = yaml.safe_load(open(path))
    case = cases[data["case_id"]]
    facts = {f.id for f in case.facts}
    assert data["case_version"] == case.version, path
    seen, per_fact = set(), collections.Counter()
    for item in data["items"]:
        assert set(item["topics"]) <= facts, (path, item)
        text = " ".join(item["utterance"].lower().split())
        assert text not in seen, (path, "duplicate", item["utterance"])
        seen.add(text)
        if len(item["topics"]) == 1:
            per_fact[item["topics"][0]] += 1
        if item["style"] == "follow_up":
            assert item.get("previous"), (path, item)
    short = {f: per_fact[f] for f in facts if per_fact[f] < 15}
    none = sum(not i["topics"] for i in data["items"])
    print(data["case_id"], len(data["items"]), "items; no-topic", none, "; short:", short)
    # Lines to re-read: words from the fact's answer that the trainee has not been told.
    told = case.candidate_instructions + " " + case.persona.opening_statement + " " + " ".join(
        f.content for f in case.facts if f.disclosure == "volunteered")
    plain = lambda t: {w for w in re.findall(r"[a-z]+", t.lower()) if len(w) >= 5}
    by_id = {f.id: f for f in case.facts}
    for item in data["items"]:
        if item["style"] == "follow_up" or not item["topics"]:
            continue
        fact = by_id[item["topics"][0]]
        labels = plain(" ".join(fact.asked_about))
        secret = plain(fact.content) - plain(told) - labels
        if plain(item["utterance"]) & secret:
            print("   CHECK", item["topics"], sorted(plain(item["utterance"]) & secret), item["utterance"])
PY
```

Additional checks passed for valid style/topic combinations, unchanged counts, brief-line
length, lower-case spoken lines, one clinical style per fact, exact case text in follow-up
replies, unique opening pairs within each fact, and punctuation/one-word near-duplicates.
A separate review of specific hidden names, numbers, locations and events found none
outside context-grounded follow-ups. Generic questions may still ask about hours, age
ranges or a 24-hour intake window; these do not supply a case's hidden numerical answer.

## Access and intended use

Repository inputs for this revision were limited to the requested Prompt C specification,
the permitted case YAML files and interpreter prompt, and the training files being revised.
The permitted station-authoring guide was already read during drafting. The prescribed
case-loader check was executed. No excluded evaluation, artifact, session, planning/paper
or fidelity-prompt files were opened or searched for this task. Only the five YAML files
and this README under `data/training/topics/` were written. Nothing was committed.

The classifier's topic decision is separate from disclosure permission. After-rapport
questions still carry their requested topic, and the application must decide separately
whether the character may disclose it. Do not turn these training phrasings into an
assessment of the classifier: keep all held-out evaluation data separate and unseen.

## Catalogue stations (2026-10-15 to 2026-10-17)

The 56 catalogue-written stations have one file each (11,099 lines): at least 15
single-fact lines per fact (four facts fell to 11-12 after overlap removal), 3-5 stacked
lines and about 35 no-topic lines including conversational openers. Drafted by Claude
subagents (Opus 5.5 for 27 stations, Sonnet for 29; see each header) from Prompt C rules,
with no access to `data/evaluation/`, which was committed first. **status: draft, not
reviewed.** 393 lines across topics and tone were then removed as near-copies (difflib
ratio at least 0.75) of the new evaluation items.

## Boundary lines (2026-10-20, Prompt H)

`<id>.boundaries.yaml` for the 56 catalogue stations: 2,719 lines (2,261 single-fact,
458 near misses with no topic) for the 229 neighbouring-fact pairs in
`data/training/boundaries/pairs.yaml`. Per pair: lines asking for one fact in the other
fact's words, both ways round, and near misses neither holds; each line records its `pair`.
Drafted by Claude Sonnet subagents with no access to `data/evaluation/`; 29 near-copies of
evaluation items removed afterwards. **status: draft, not reviewed.** Part B of
docs/STUDENT-CROSS-CHECK-PLAN.md.
