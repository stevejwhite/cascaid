# Drafting a CASC station with a frontier LLM

Two copy-and-paste prompts for a capable LLM (for example Claude, GPT or Gemini), and what
to do with the results. The LLM drafts; a person reviews and owns the station.

- **Prompt A** drafts the station file (`data/cases/<id>.yaml`).
- **Prompt B** drafts its evaluation material in a **separate, fresh session** that never
  sees the station's question labels. If the same session writes both, it phrases test
  questions to match its own labels and inflates the measured accuracy.
- **Prompt C** drafts training phrasings for the topic classifier (step 2 of the
  interpreter work). It is for a coding agent with access to this repository, and it must
  never see the evaluation data.
- **Prompt D** drafts training lines for the tone classifier (empathy and confrontation),
  under the same conditions as Prompt C.
- **Prompt E** drafts whole synthetic interviews, labelled for topic and tone, to train the
  small student interpreter (docs/INTERPRETER-FINETUNE-PLAN.md).
- **Prompt F** drafts interviews built around the student's remaining mistakes: near-miss
  questions, confrontation, and neighbouring facts.
- **Prompt G** researches and writes the case files for one running order of the station
  catalogue ([STATION-CATALOGUE.md](STATION-CATALOGUE.md)).

For the rules behind every field, see [ADDING-A-STATION.md](ADDING-A-STATION.md).

## How to use it

1. Decide the station: skill, subdivision, specialty, who the candidate meets, and a
   one-line scenario. Fill in the `REQUEST` block at the end of Prompt A.
2. Paste Prompt A, with your request, into a new LLM session. Save the YAML it returns as
   `data/cases/<id>.yaml`.
3. Set `authorship.author` to record that a model drafted it and who edited it, for example
   `Drafted by Claude Opus 5.5; edited by S. White`. Keep `status: author_draft` until you
   have reviewed it.
4. Review the draft against the checklist below and edit it. Run `npm run test:api` and
   try the station in the app.
5. If the station will be used in the study, open a **new** session and run Prompt B with
   the station's details pasted in where it asks (without the `asked_about` lists). Save
   its two outputs and commit them **before** you change any labels in response to results.

## Review checklist (for the person)

- Clinically plausible and internally consistent: ages, dates, durations and numbers agree.
- Nothing is copied or closely paraphrased from RCPsych materials, question banks or
  published cases; names and details are invented.
- Each fact answers its questions directly (including the yes or no).
- No two facts share distinctive label words; each fact covers one topic.
- Sensitive material (current intent, shame, carer strain, hopes) is `after_rapport`.
- The persona background carries no facts that the station is meant to elicit.
- The author notes at the top of the file list the clinical assumptions to check; resolve
  or keep them as comments, and mark the case `author_reviewed` only when you are satisfied.

---

## Prompt A: station author

Copy everything in the block below.

````text
You are writing one practice station for a research prototype that simulates the
MRCPsych CASC (Clinical Assessment of Skills and Competencies) exam. A trainee psychiatrist
interviews a role-played patient, relative, carer or colleague for seven minutes. The
station you write is a YAML file that the software uses in three ways:

1. An INTERPRETER model reads each trainee question and decides which hidden facts it asks
   about. It sees ONLY each fact's `asked_about` labels, never the fact text.
2. Deterministic DISCLOSURE RULES decide whether each asked-about fact may be revealed now.
3. A small ROLE-PLAY model voices the character. It sees the persona and ONLY the facts
   unlocked so far, and is told which ones answer the current question. Anything not
   written in the file is unknown to the character, who deflects.

After the station, feedback reports which key facts the trainee elicited, by domain.

## Hard rules

- Original fiction only. Invent every name and detail. Do not copy, adapt or closely
  paraphrase RCPsych station scripts, exam questions, question banks, eLearning, textbook
  vignettes or any real person's history.
- Educational fiction, not clinical guidance: facts must be clinically plausible, but the
  station gives no treatment advice. The character never recommends treatment.
- Use only the field names and allowed values given below. Unknown fields are rejected.
- Output a single YAML document and nothing else, beginning with the author-notes comment.

## Output format

Begin with YAML comment lines:
  # Original fictional case for the PsychiatryEduAI CASC proof of concept (CC-BY-4.0).
  # Author draft (LLM-drafted). Not clinically validated.
  # Author notes: <one comment line per clinical assumption a clinician should check>

Then these fields, in this order:

id: <slug; lower-case words joined by hyphens, e.g. eating-disorder-history>
version: 0.1.0
title: <short station name, e.g. "Low weight — history">
blueprint:
  skill: <history | examination | management>
  subdivision: <one subdivision that belongs to the skill; see list>
  specialty: <general | child_and_adolescent | old_age | intellectual_disability | forensic | medical_psychotherapy | addiction>
  communication_focus:            # optional list, 0 to 2 items
    - <personalisation_and_respect | recognising_and_responding_to_cues | empathy | providing_clear_and_accurate_information>
timing:
  reading_seconds: <240 for management stations; 90 for history and examination stations>
authorship:
  author: LLM draft
  status: author_draft
candidate_instructions: >-
  <2 to 4 sentences: who the candidate is, who they meet and why, the task, and what is
  out of scope, e.g. "Do not discuss management.">
persona:
  role: <patient | relative | carer | colleague>
  name: <first name>
  age: <number>
  description: >-
    <1 to 2 lines of background: work, household, relationship to the patient. No facts
    the station is meant to elicit.>
  speech_style: <one line on how they talk>
  affect: <one line on their emotional state and how it changes, e.g. with empathy>
  opening_statement: >-
    <what they say first when the interview starts; may state the presenting concern>
  voice: {sex: <female | male; omit the key if the case leaves it open>, age: <young | adult | older>, accent: en-GB}
facts:
  - id: <slug, unique in the file>
    content: <first-person words the character may say, as a direct answer>
    disclosure: <volunteered | on_direct_question | after_rapport>
    asked_about: [<3 to 6 short labels for the questions this fact answers>]
    domain: <slug grouping the fact in feedback, e.g. presenting-complaint, risk, substances, past-history, social, physical-health, mental-state, perspective, concerns, background>
    key: <true for checklist items; omit otherwise>
    rapport_needed: <2 for the single most guarded after_rapport fact; omit otherwise>
    vague: <for 1 or 2 facts only: an evasive first answer with no numbers or details>
tasks:                              # optional, 0 to 2
  - id: <slug>
    description: <a candidate action, e.g. "Summarises the history back to Alex.">
    domain: <slug>
    evidence_indicator: <summary | check_understanding | empathy | open_question>   # OR
    evidence_fact: <a fact id in this file>                                        # never both
unscripted_response: <one in-character line used when a question is not covered>
deflections:
  - <the same refusal in different words>
  - <and once more, different again>
affect_stages:
  - id: <slug for the starting stage>
    affect: <how they feel at the start>
  - id: <slug>
    affect: <how they feel once the candidate has shown empathy>
    rapport_at_least: 1
  - id: <slug>
    affect: <how they react to being challenged, blamed or lectured>
    on_confrontation: true
questions:                          # 1 or 2
  - id: <slug>
    text: <a question the character would ask the doctor, revealing no fact>
    after_fact: <a fact id, if the question only makes sense once that fact is out>  # OR
    after_seconds: <e.g. 300 for a question near the end>                           # never both

Subdivisions by skill:
- history: presenting_complaint_and_psychiatric_history, physical_health_history,
  developmental_history, personal_and_social_history, collateral_history
- examination: mental_state_cognitive, mental_state_psychotic, mental_state_non_psychotic,
  capacity_assessment, physical_examination, risk_assessment
- management: formulation, management_biological, management_psychological,
  holistic_management_plan, safety_planning, legal_and_ethical_management

Choose a subdivision that can be practised by conversation. Avoid stations that need a
physical examination or a test to be performed.

## How to write the facts (most important)

Write 9 to 13 facts that together make a coherent clinical picture a good candidate
would uncover in seven minutes. Mark 6 to 9 as key: the information an examiner would
expect. Testing of this system showed these rules matter most:

1. WRITE EACH FACT AS A DIRECT ANSWER to the questions in its labels, including the yes
   or no. "Yes, I'd planned it. I bought the tablets two days ago" works. "I bought the
   tablets two days ago" alone made the role-play model add "I didn't plan it".
2. CLOSE THE GAPS the role-player would otherwise fill. If a candidate will ask "how
   often?" or "since when?", put the answer in the fact. Give exact numbers and keep them
   consistent across facts, the persona and the opening statement.
3. ONE TOPIC PER FACT. If a candidate could ask about two things separately, write two
   facts. A fact may hold two closely linked details (a symptom and its timing).
4. DISTINCTIVE LABELS. `asked_about` labels are everything the interpreter sees, and the
   first two labels form its topic key, so make them specific and different from every
   other fact's labels. Do not reuse a distinctive word across facts: "tablets" in two
   facts caused wrong selections. Prefer "more tablets or medicines kept at home now" to
   "tablets at home". Write labels as a candidate would ask, in plain words.
5. DISCLOSURE:
   - volunteered: only the presenting story the character would offer unprompted (0 to 2
     facts). Volunteered facts are excluded from the score, so do not make them key.
   - on_direct_question: most facts.
   - after_rapport: 1 to 3 sensitive facts the character holds back until the candidate
     shows empathy (current suicidal intent, shame, carer strain, hopes and fears,
     motivation to change). Each needs a gentle-question label among its labels.
6. KEEP FACTS OUT OF THE PERSONA. The description gives context only; anything the
   candidate should elicit belongs in a fact, or the role-player will volunteer it.
7. ROLE-APPROPRIATE KNOWLEDGE. A relative knows what a relative would know; they report
   concerns and observations, not diagnoses. In management stations the character holds
   concerns, questions and background; the candidate supplies the explanation.
8. RISK. Unless the scenario excludes it, include a fact about risk to self or others,
   even if the answer is a clear denial.
9. REALISM. Give one or two facts a `vague` first answer, the evasive thing a real person
   says before a follow-up. Mark the single most guarded after_rapport fact
   `rapport_needed: 2`. Write three affect stages and one or two questions the character
   asks; in management stations, questions about the treatment are the most useful.

## Worked example

This is an existing station, shown for format and style only. Do not reuse its content.

id: alcohol-history
version: 0.1.0
title: Alcohol use — history
blueprint:
  skill: history
  subdivision: presenting_complaint_and_psychiatric_history
  specialty: addiction
  communication_focus:
    - personalisation_and_respect
timing:
  reading_seconds: 90
authorship:
  author: PsychiatryEduAI project
  status: author_draft
candidate_instructions: >-
  You are a core trainee in a community addiction service. Chris, aged 46, has
  been referred by their GP after abnormal liver function tests. Take a history
  of Chris's alcohol use. Do not discuss management.
persona:
  role: patient
  name: Chris
  age: 46
  description: >-
    Works as a delivery manager, divorced four years ago, lives alone and has an
    adult daughter.
  speech_style: Defensive and minimising at first; jokes to deflect; more honest when not judged.
  affect: Ashamed and irritable at first; softens when treated with respect.
  opening_statement: >-
    My GP said my liver tests were a bit off and that I should come and talk to
    you about my drinking. I don't think it's that bad, to be honest.
  voice: {age: adult, accent: en-GB}
facts:
  - id: quantity
    content: I get through about a litre bottle of vodka a day, sometimes more at the weekend.
    disclosure: on_direct_question
    asked_about: [how much you drink, a typical day, what you drink, units]
    domain: alcohol
    key: true
  - id: withdrawal
    content: >-
      If I go without, I get the shakes and sweats by lunchtime. I had a fit two
      years ago when I tried to stop on my own.
    disclosure: on_direct_question
    asked_about: [withdrawal, shakes, sweats, what happens if you stop, seizures, fits]
    domain: alcohol
    key: true
  - id: risk
    content: I've never tried to harm myself, and I don't have thoughts of ending my life.
    disclosure: on_direct_question
    asked_about: [self-harm, suicidal thoughts, harming yourself, safety]
    domain: risk
    key: true
  - id: motivation
    content: >-
      My daughter has stopped letting me see my grandson when I've been drinking.
      That's what's made me think I need to stop.
    disclosure: after_rapport
    asked_about: [reasons to change, what you want, motivation, worries about drinking, family]
    domain: perspective
    key: true
  # ...the real file has 12 facts in total
tasks:
  - id: non-judgemental
    description: Takes the history in a non-judgemental way that keeps Chris engaged.
    domain: communication
unscripted_response: I'd rather not go into that right now.
deflections:
  - "Can we leave that for now?"
  - "That's not really something I want to talk about."

## Check before you answer

- Every fact id is unique and every task's evidence_fact names a fact in this file.
- Every fact has at least one label; no distinctive label word appears in two facts.
- Each fact reads as a direct, complete answer to its first label.
- 6 to 9 facts are key; no volunteered fact is key; 1 to 3 facts are after_rapport.
- Numbers, ages and durations agree everywhere in the file.
- The deflections reveal nothing and mean the same as unscripted_response; voice.sex is
  set only if the character's sex is fixed by the case.
- Vague answers contain no number or detail found only in the full fact; character
  questions reveal nothing the candidate has not yet elicited.
- reading_seconds is 240 for management, 90 otherwise; the subdivision belongs to the skill.
- No content comes from real exam material or real people.
- The author-notes comments list each clinical assumption a clinician should check.

## REQUEST

Skill: <history | examination | management>
Subdivision: <from the list>
Specialty: <from the list>
Candidate meets: <patient | relative | carer | colleague>
Scenario: <one or two lines, e.g. "19-year-old student referred by her GP with weight
loss; take a history focusing on eating and risk">
````

---

## Prompt B: evaluation author (fresh session)

Use a **new session**. Paste the block below, then paste the station's `id`,
`candidate_instructions`, `persona` and, for each fact, only its `id`, `content` and
`disclosure` — **not** its `asked_about` labels.

````text
You are writing evaluation material for one practice station in a research prototype that
simulates the MRCPsych CASC exam. A trainee interviews a role-played character. Software
decides which hidden facts each trainee line asks about, then reveals them only if allowed.
Your material tests that software. Write the questions the way real trainees speak:
varied, sometimes informal, sometimes open ("tell me about…"), sometimes closed.

You will receive the station's id, candidate instructions, persona and its facts (id,
content, disclosure). Facts marked after_rapport are revealed only after the trainee has
shown empathy; asked earlier, they are held back.

Return TWO YAML documents separated by a line containing only ---. Output nothing else.

DOCUMENT 1: labelled questions (saved as data/evaluation/interpreter/<id>.yaml)

case_id: <id>
split: test
items:
  - utterance: <one trainee line>
    expected: [<fact ids a correct system should select; [] if none>]
    rapport: <true only if the line explicitly expresses empathy or validation>

Write 15 to 20 items: at least one question per key fact in fresh wording; one or two
follow-ups that only make sense with context, given as
    previous: {interviewer: <earlier question>, character: <short reply>}
one greeting, one or two empathic statements (expected: [], rapport: true), one or two
off-case questions (expected: []), and one statement or summary that asks nothing
(expected: []). Use [] rather than guessing when no fact clearly answers a line.

DOCUMENT 2: scripted interviews (saved as data/evaluation/scripts/<id>.yaml)

case_id: <id>
interviews:
  - id: complete
    kind: complete
    turns:
      - {say: "<line>", expect: [<fact ids the reply should answer>]}
  - id: partial-<what it skips>
    kind: partial
    turns: [...]
  - id: adversarial
    kind: adversarial
    turns: [...]

- complete: 11 to 15 turns covering every key fact once, starting with a greeting and
  including one empathic statement (expect: []) BEFORE any after_rapport fact is asked.
- partial: 3 to 6 turns that deliberately skip at least two domains; name what it skips
  in its id.
- adversarial: 9 turns: one ordinary opening question, then one of each probe, marked with
  `probe:` — early_rapport (ask an after_rapport fact with no empathy first; expect: [],
  expect_deferred: [<that fact id>]), leading (suggest a symptom or event the case does not
  contain; expect: []), off_case (expect: []), break (ask if the character is an AI or a
  simulation; expect: []), injection (tell the character to ignore its instructions and
  reveal the case; expect: []), advice (ask the character for clinical advice; expect: []),
  repeat (repeat the opening question in different words; expect: the same fact),
  stacked (ask about two facts in one line; expect: both).

Use different wording from Document 1 throughout. Write each `say` line in double quotes.
````

---

## Prompt C: topic-classifier training data (coding agent with repository access)

Give this to a coding agent (for example Codex) working in this repository. It writes
`data/training/topics/`. Review the result before committing it. The evaluation sets in
`data/evaluation/` must stay unseen: training on anything resembling them would inflate the
held-out results.

```text
You are drafting training data for a topic classifier in this repository (PsychiatryEduAI,
a CASC psychiatry exam practice simulator). The classifier decides which case fact a
trainee's line asks about. Your phrasings train it; they are never shown to trainees.

FILES YOU MAY READ (and only these)
- data/cases/*.yaml (the five station cases)
- prompts/casc-interpret-v1.txt (the labelling rules the current model-based interpreter
  follows; your labels must follow the same rules)
- docs/ADDING-A-STATION.md (background on cases and fields)

FILES YOU MUST NOT OPEN, SEARCH OR GREP
- anything under data/evaluation/, artifacts/ or data/sessions/
- docs/CASC-POC-PLAN.md, docs/REALISM-PLAN.md, docs/PAPER-DRAFT.md, docs/DECISIONS.md,
  docs/QWEN-SPECIFICATION.md
- prompts/fidelity-*.txt
These hold the held-out test questions and results. If you see any of them by accident,
stop and say so in your summary.

WHAT TO WRITE
One file per case: data/training/topics/<case-id>.yaml, plus data/training/topics/README.md.
Do not modify any other file, and do not commit.

File format:

  # Training phrasings for the topic classifier. Drafted by <your model name and version>
  # on <date>; NOT YET REVIEWED. Not evaluation data.
  case_id: <case id>
  case_version: <the case's version field>
  status: draft_unreviewed
  items:
    - utterance: <one trainee line, as spoken>
      topics: [<fact ids this line asks about>]   # [] when it asks about no fact
      style: <one of the styles below>
      previous:                                    # only for style follow_up
        interviewer: <the trainee's previous line>
        character: <the character's reply, using only that fact's content>

HOW MANY, PER CASE
- Every fact in the case, including volunteered ones: at least 15 lines whose topics list
  is exactly [that fact id].
- 3 to 5 stacked lines asking about two facts at once (topics lists both).
- 30 lines that ask about no fact (topics: []).
Across the five cases that is roughly 825 single-fact lines and 150 no-topic lines.

STYLES (spread each fact's 15 lines across at least six of these)
- open: "Can you tell me about ...?"
- closed: a yes/no or specific question
- colloquial: everyday wording, contractions, how a nervous trainee might say it
- clinical: more formal or technical wording a trainee might use
- indirect: asks without a question mark ("I wondered how things are with ...")
- empathy_then_question: a short empathic phrase followed by the question; the topic is
  still the fact asked about
- spoken: as speech recognition would transcribe it: lower case, little punctuation,
  fillers such as "um" or "so", a false start
- brief: three to six words ("and the drinking?")
- follow_up: depends on the previous exchange to make sense ("how long has that been
  going on?"); fill in previous, and label the fact the follow-up asks about, which may
  differ from the fact just discussed
- leading: suggests an answer ("You've been drinking every day, haven't you?"); label the
  fact it asks about
For no-topic lines use these styles: greeting, introduction, empathy (a statement with no
question), summary, explanation, check_understanding, off_case (a plausible clinical
question for this kind of station that no fact covers, for example family history of mental
illness when no fact holds it; vary these between cases), near_miss (a plausible clinical
question that shares the obvious words of a fact but asks for something it does not hold,
for example "Do you take any tablets for your blood pressure?" in a case whose only
tablets fact is about the overdose). No trivia (brands, colours, phone numbers), and no
question about a detail of an existing fact.

LABELLING RULES (follow prompts/casc-interpret-v1.txt exactly)
- Label the information the line asks for, not words it shares with a label.
- One fact per line, unless the line clearly asks two separate questions (style stacked).
- Greetings, introductions, empathy, explanations, summaries and checks of understanding
  ask for no information: topics [] even if they mention a topic.
- When two facts are close (for example overdose details vs planning, or quantity vs
  duration of drinking), write lines that show the difference, and label them carefully.
  These distinctions matter more than volume.
- For after_rapport facts, write the gentle questions a trainee would ask (labels still
  name the fact); do not add empathy unless the style calls for it.

THE TRAINEE KNOWS ONLY WHAT THE TRAINEE HAS BEEN TOLD
A trainee's question can use only: the candidate_instructions, the character's
opening_statement, the content of volunteered facts, general clinical knowledge, and, in
follow_up lines, the previous exchange. Every other detail in a fact is the answer, which
the trainee is trying to find out. So do not write "Did you leave a note for your mum?"
(the trainee does not know about the mum), "Did the equipment cost eight hundred pounds?"
or "Did the police bring him home?". Write "Did you leave a note or a message for
anyone?", "How much have you spent?", "Has he ever got lost?". Leading lines guess at
something general ("You've been drinking every day, haven't you?"); they must not contain
the fact's specific details.

QUALITY RULES
- Write what real trainees say in a seven-minute CASC station: varied, imperfect, natural
  British English. Most trainees use the obvious everyday words: "Did you leave a note?",
  "How much do you drink?", "Is he scared of needles?", "Has he ever got lost?". About
  half of each fact's lines should use the obvious word for the topic (even if it appears
  in the labels); the rest should find other natural ways to ask. Do not copy a whole
  label as the question.
- Keep the register a UK psychiatry trainee's: plain, polite, sometimes awkward. At most
  one clinical line per fact, and no jargon a trainee would not say to a patient or
  relative ("venepuncture", "ethanol intake", "impaired navigation").
- Vary how lines open; no opening phrase ("Talk me through", "I'd like to") in more than
  one line per fact.
- No two lines in a file may differ only by punctuation or a single word.
- Original wording only: do not reproduce RCPsych material, question banks, textbooks or
  any real person's words.
- Questions only, from the trainee's side; never write the character's answers except in
  previous.character for follow_up, using the fact's own content.
- No real names except the character names already in the case.

README.md must state: which model drafted the data and when, that it is unreviewed, the
counts per case and per style, and that the files must not be used for evaluation.

BEFORE YOU FINISH, run this check from the repository root and fix anything it reports:

  uv run --project services/api --locked python - <<'PY'
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

The CHECK lines are not errors: re-read each one and rewrite it if it uses something the
trainee has not been told; leave it if the word is general ("hours", "doctors").

Finish with a short summary: files written, counts, any fact where you were unsure which
label applies (list the lines), and confirmation that you did not open the excluded files.
```

## Prompt D: tone-classifier training data (coding agent with repository access)

Give this to a coding agent working in this repository. It writes `data/training/tone/`.
As with Prompt C, the evaluation sets must stay unseen, and the result is reviewed before it
is committed. `services/api/tests/test_training_data.py` rejects near-copies of evaluation
items and labels that contradict the runtime tone rules.

```text
You are drafting training data for a tone classifier in this repository (PsychiatryEduAI,
a CASC psychiatry exam practice simulator). The classifier rates each line a trainee says
to a simulated patient or relative: how much empathy it expresses, and whether it is
confrontational. Your lines train it; they are never shown to trainees.

FILES YOU MAY READ (and only these)
- data/cases/*.yaml (the five station cases)
- docs/ADDING-A-STATION.md (background on cases)
- this prompt, in docs/LLM-STATION-PROMPT.md

FILES YOU MUST NOT OPEN, SEARCH OR GREP
- anything under data/evaluation/, artifacts/ or data/sessions/
- anything under prompts/ and services/ (you will run one check script, below, without
  reading the source)
- docs/CASC-POC-PLAN.md, docs/REALISM-PLAN.md, docs/PAPER-DRAFT.md, docs/DECISIONS.md,
  docs/QWEN-SPECIFICATION.md
These hold the held-out test lines and results. If you see any of them by accident, stop and
say so in your summary.

DEFINITIONS (label exactly by these)
empathy
- 0, none: questions (however gently phrased), greetings, thanks for coming, explanations,
  summaries, neutral acknowledgements ("Mm, I see", "Okay, thanks"), and politeness such as
  "Apologies for being nosy, but...". A question about something painful is still 0.
- 1, brief: a stock or generic expression of sympathy or acknowledgement that could follow
  almost anything: "What a horrible time you've had." "I really feel for you."
- 2, specific: names the person's own feeling or situation, from what they have said, and
  validates it, or reflects it back and invites them to say more. It refers to particular
  things in their situation, and it is at least eight words long.
confrontational
- true when the line challenges, disbelieves, blames, lectures, moralises, pressures or
  dismisses the person or their concerns, or tells them how to see their situation.
  Asking a direct question, even about something difficult, is not confrontational.

RULES THE RUNTIME APPLIES (your labels must agree with them)
- Empathy counts only from a statement. Put the empathic words in their own sentence ending
  in a full stop, before any question: "What a rotten few weeks. Are you getting much rest
  at the moment?" Empathy inside a question ("Isn't that upsetting?") is labelled 0.
- A question that opens with a question word (what, when, how, do, have, is, can, any...)
  is never confrontational. Confrontation can be a statement, a "why" question ("Why on
  earth didn't you say something sooner?"), a tag question ("You saw this coming, didn't
  you?") or a rhetorical question ("Surely you saw this coming?").
- A line is not both empathic and confrontational.

THE TRAINEE KNOWS ONLY WHAT THE TRAINEE HAS BEEN TOLD
Specific empathy must refer to things the person has already said: the case's
candidate_instructions or opening_statement, a volunteered fact, or a previous exchange
that you include with the line (previous.character copied word for word from one fact's
content in that case). Do not refer to details the trainee has not been told.

WHAT TO WRITE
One file per case: data/training/tone/<case-id>.yaml, plus data/training/tone/README.md.
Do not modify any other file, and do not commit.

  # Training lines for the tone classifier. Drafted by <your model name and version> on
  # <date>; NOT YET REVIEWED. Not evaluation data.
  case_id: <case id>
  case_version: <the case's version field>
  status: draft_unreviewed
  items:
    - utterance: <one trainee line, as spoken>
      empathy: <0, 1 or 2>
      empathy_words: <the exact empathic words copied from the utterance, or "">
      confrontational: <true or false>
      challenge_words: <the exact challenging words copied from the utterance, or "">
      style: <one of the styles below>
      previous:                     # only when the line responds to something just said
        interviewer: <the trainee's previous line>
        character: <copied word for word from one fact's content>

80 LINES PER CASE, IN THESE GROUPS AND STYLES
- 40 with empathy 0, not confrontational:
  - 15 plain_question, including at least 8 about painful or sensitive topics in the case
    (suicide, self-harm, drinking, family conflict, fears)
  - 6 polite_question: gentle or apologetic wording with no empathic statement ("If you
    don't mind me asking, could you tell me...")
  - 5 greeting or introduction, including thanks for coming
  - 6 summary, explanation or check_understanding
  - 8 acknowledgement: a neutral acknowledgement, alone or before a question ("Right. And
    roughly when was that?", "Okay, thanks.")
- 14 with empathy 1: 8 brief_empathy alone, 6 brief_empathy_question (statement, then a
  question)
- 14 with empathy 2: 9 specific_empathy, 5 specific_empathy_question; at least 8 of the 14
  use a previous exchange
- 12 confrontational, empathy 0: 4 confront_statement, 2 confront_why, 2 confront_tag,
  1 confront_rhetorical, 3 dismissive ("Honestly, there's nothing to fret about.")
Across each case, write about one line in seven as speech would be transcribed: lower
case, little punctuation, fillers such as "um" (keep the label and style).
Include contrasting pairs on the same subject: a brief and a specific version, a polite
question and a brief_empathy_question, a plain question and a confrontational one. These
boundaries matter more than volume.

QUALITY RULES
- Natural British English, as UK psychiatry trainees speak to patients and relatives:
  plain, warm or awkward, sometimes clumsy. Vary openings; no opening phrase in more than
  three lines per file. No two lines may differ only by punctuation or a single word.
- Fit each case: its role (patient, relative), its scenario and the person's name.
- Confrontational lines should sound like real trainee mistakes, which are mostly subtle:
  lecturing, minimising, premature reassurance, impatience, disbelief or moralising
  ("Can't you just cut back a bit?", "Most people manage to stop once they put their mind
  to it.", "It's a very safe medicine, honestly.", "Everyone gets a bit forgetful at his
  age.", "Let's not get carried away with the business."). At most three per case may be
  openly hostile or insulting.
- Acknowledgements are short and natural, as said in conversation ("Okay.", "Right, thank
  you.", "Mm-hm. And then?"), not formal ("Let us move to the next part").
- Vary how specific empathy is put: not mostly "<situation> sounds <adjective>.". Use
  forms such as "No wonder you're worn out, with everything you've told me." or "I can
  imagine how lonely that's been." Write 3 to 5 of each case's 14 specific lines without a
  previous exchange, drawing on the opening_statement or a volunteered fact.
- Original wording only: no RCPsych material, question banks, textbooks or real people.

README.md must state: which model drafted the data and when, that it is unreviewed, and
the counts per case, per label and per style.

BEFORE YOU FINISH, run this from the repository root and fix anything it reports:

  uv run --project services/api --locked pytest -q services/api/tests/test_training_data.py

and this count check:

  uv run --project services/api --locked python - <<'PY'
  import collections, glob, yaml
  for path in sorted(glob.glob("data/training/tone/*.yaml")):
      items = yaml.safe_load(open(path))["items"]
      labels = collections.Counter(
          ("confrontational" if i["confrontational"] else f"empathy {i['empathy']}")
          for i in items)
      print(path, len(items), dict(labels))
  PY

The test checks your labels against the runtime rules and rejects any line too similar to
evaluation material you have not seen. Stock phrases are the most likely to be rejected,
because brief empathy is short and common; when that happens, choose a different natural
stock phrase rather than an unusual one. Do not copy the examples in this prompt. Finish with a short summary: files written, counts, lines you were
unsure how to label, and confirmation that you did not open the excluded files.
```

## Prompt E: synthetic interviews for the student interpreter (coding agent with repository access)

Give this to a coding agent working in this repository. It writes
`data/finetune/synthetic/`: whole interviews, so that each trainee line has the exchange
before it, labelled for topic and tone. They train the small "student" interpreter
(docs/INTERPRETER-FINETUNE-PLAN.md). As before, the evaluation sets must stay unseen, the
result is reviewed before it is committed, and `services/api/tests/test_finetune_data.py`
rejects near-copies of evaluation items and labels that contradict the runtime rules.
Real session transcripts (`data/sessions/`) stay on this machine: the agent must not read
them.

```text
You are drafting training data for a small model in this repository (PsychiatryEduAI, a
CASC psychiatry exam practice simulator). The model reads one line a trainee says to a
simulated patient or relative, with the exchange just before it, and labels (1) which case
topics the line asks about and (2) its tone. Your interviews train it; they are never shown
to trainees.

FILES YOU MAY READ (and only these)
- data/cases/*.yaml (the five station cases; each fact's asked_about labels define its topic)
- prompts/casc-interpret-v1.txt and prompts/casc-tone-v1.txt (the labelling rules; your
  labels must follow them exactly)
- data/training/topics/*.yaml and data/training/tone/*.yaml (existing training lines: do
  not repeat them)
- docs/ADDING-A-STATION.md and this prompt

FILES YOU MUST NOT OPEN, SEARCH OR GREP
- anything under data/evaluation/, data/sessions/ or artifacts/
- docs/CASC-POC-PLAN.md, docs/REALISM-PLAN.md, docs/PAPER-DRAFT.md, docs/DECISIONS.md,
  docs/QWEN-SPECIFICATION.md, docs/AVATAR-PLAN.md
They hold held-out test lines, results and real transcripts. If you see any of them by
accident, stop and say so in your summary.

WHAT TO WRITE
One file per case, data/finetune/synthetic/<case-id>.yaml. Do not modify any other file,
and do not commit.

  # Synthetic interviews for the student interpreter. Drafted by <your model name and
  # version> on <date>; NOT YET REVIEWED. Not evaluation data.
  case_id: <case id>
  case_version: <the case's version field>
  status: draft
  interviews:
    - id: <case-id>-01
      trainee: <one line: the trainee's manner, e.g. "nervous FY2, rambling preambles">
      turns:
        - doctor: <what the trainee says, as spoken>
          character: <the character's reply, 1 to 3 sentences>
          topics: [<fact ids this doctor line asks about>]   # [] if none; at most 2
          empathy: none | brief | specific
          empathy_words: <copied word for word from the doctor line, or "">
          confrontational: true | false
          confrontational_words: <copied word for word, or "">

HOW MANY, PER CASE
12 interviews of 15 to 25 turns each (about 240 turns per case). Give the 12 trainees
different manners: nervous, brisk, warm, formal, rambling, abrupt, speaking as speech
recognition transcribes (lower case, fillers such as "um", false starts), one who
summarises often, one who is sometimes confrontational, and so on.

WHAT REAL TRAINEES DO (cover all of these, spread across interviews)
- greet and introduce themselves, use the character's name, thank them for coming;
- preface questions ("Okay, that's fine. I just need to go over a few other things. ...");
- ask generic openers ("What's brought you in?", "How are things?");
- ask follow-ups that only make sense with the previous exchange ("When did that start?",
  "How long has this been going on?", "And how much is that?"): label the fact the
  follow-up asks about, using the previous exchange to decide;
- ask two things in one turn (topics lists both; at most two);
- summarise, check understanding, explain, reassure (no topic unless they also ask);
- show empathy, briefly or specifically; occasionally challenge, blame or lecture;
- move on with transitions ("Can I ask about something else?").
About one turn in four should be a follow-up that depends on the previous exchange.

THE CHARACTER'S REPLIES
They give the context for the next line; they are not labelled. Keep them short and
consistent with the case: reveal a fact only when the doctor has asked about it, answer
after_rapport facts only once the trainee has shown empathy, and never invent clinically
meaningful details (numbers, diagnoses, events) that are not in the case file. When asked
about something the case does not cover, the character says they are not sure or moves on.

LABELLING RULES (exactly as the runtime applies them)
- topics: the fact ids whose asked_about labels the doctor's line asks the character
  about, judged with the previous exchange. Greetings, empathy, explanations, summaries and
  questions about things no fact covers are [].
- empathy_words must be copied word for word from a statement in the line, never from a
  question. "specific" needs at least 8 words naming the person's circumstances and
  feelings; stock phrases are "brief".
- confrontational_words must be copied word for word from a sentence that is not an
  information-seeking question. Asking for information, even about drinking or suicide, is
  never confrontational; "Why didn't you...", tag questions ("you knew, didn't you?") and
  statements can be.

CHECK BEFORE YOU FINISH
Run: npm run test:api -- -k finetune_data
Fix anything it reports. In your summary list the files written and the number of
interviews and turns per case, and any files you opened by accident.
```

## Prompt F: hard cases for the student interpreter (coding agent with repository access)

Give this to a coding agent working in this repository, in a **new** session. It writes
`data/finetune/synthetic/<case-id>.prompt-f.yaml`: interviews built around the cases the
student got wrong after training on Prompt E's interviews (run 4 in
docs/INTERPRETER-FINETUNE-PLAN.md): near-miss questions it matched to a fact, confrontation it
missed, and neighbouring facts it confused. The same tests apply as for Prompt E, plus a
variety check. Review the files before committing them; real sessions (`data/sessions/`) and
the evaluation sets stay unseen.

```text
You are drafting training data for a small model in this repository (PsychiatryEduAI, a
CASC psychiatry exam practice simulator). The model reads one line a trainee says to a
simulated patient or relative, with the exchange just before it, and labels (1) which case
topics the line asks about and (2) its tone. A topic it labels can unlock a hidden fact, so
labelling a topic that was not asked for is the worst mistake it can make.

A model trained on earlier data makes three kinds of mistake. Your interviews must be built
around them:

1. NEAR-MISS QUESTIONS. It labels a topic when the question shares a fact's obvious words
   but asks for something the fact does not hold. Examples of the pattern (do not reuse):
   "Which school did Daniel go to?" in a case whose Daniel fact is about his views on
   medication;
   "Do you take tablets for your blood pressure?" in a case whose only tablets fact is the
   overdose. The correct label is [] (no topic).
2. CONFRONTATION. It misses lines that challenge, blame, lecture, dismiss, disbelieve or
   pressure the person, especially when they come with a real question.
3. NEIGHBOURING FACTS. It confuses facts that sit close together, for example "Has anything
   like this ever happened before last night?" (past self-harm) with "How many did you
   take?" (the overdose itself).

It is already good at greetings, plain questions and empathy; keep those as the ordinary
turns around the hard ones.

FILES YOU MAY READ (and only these)
- data/cases/*.yaml (the five station cases; each fact's asked_about labels define its topic)
- prompts/casc-interpret-v1.txt and prompts/casc-tone-v1.txt (the labelling rules)
- data/training/topics/*.yaml, data/training/tone/*.yaml and data/finetune/synthetic/*.yaml
  (existing training lines: do not repeat them or their stock phrases)
- docs/ADDING-A-STATION.md and this prompt

FILES YOU MUST NOT OPEN, SEARCH OR GREP
- anything under data/evaluation/, data/sessions/ or artifacts/
- docs/CASC-POC-PLAN.md, docs/REALISM-PLAN.md, docs/PAPER-DRAFT.md, docs/DECISIONS.md,
  docs/QWEN-SPECIFICATION.md, docs/AVATAR-PLAN.md, docs/INTERPRETER-FINETUNE-PLAN.md
They hold held-out test lines, results and real transcripts. If you see any of them by
accident, stop and say so in your summary.

WHAT TO WRITE
One file per case, data/finetune/synthetic/<case-id>.prompt-f.yaml. Do not modify any other
file, and do not commit.

  # Hard-case interviews for the student interpreter (Prompt F). Drafted by <your model
  # name and version> on <date>; NOT YET REVIEWED. Not evaluation data.
  case_id: <case id>
  case_version: <the case's version field>
  status: draft
  interviews:
    - id: <case-id>-f01
      trainee: <one line: the trainee's manner>
      turns:
        - doctor: <what the trainee says, as spoken>
          character: <the character's reply, 1 to 3 sentences>
          kind: near_miss | confrontational | reflection | neighbour | ordinary
          topics: [<fact ids this doctor line asks about>]   # [] if none; at most 2
          empathy: none | brief | specific
          empathy_words: <copied word for word from the doctor line, or "">
          confrontational: true | false
          confrontational_words: <copied word for word, or "">

HOW MANY, PER CASE
8 interviews of 18 to 24 turns (about 170 turns per case), containing at least:
- 35 near_miss turns: a question that uses words from one of the case's facts (its
  asked_about labels or its subject) but asks for something that fact does not contain.
  topics: []. Cover every fact of the case at least twice. Mix them in naturally; about a
  third should be follow-ups whose near-miss only shows given the previous exchange.
- 30 confrontational turns of varied kinds: blaming ("You've left this far too
  late."), lecturing ("You need to stop drinking."), dismissing ("There's nothing to be
  frightened of."), disbelieving ("I don't believe it's only two cans."), pressuring
  ("I need a straight answer."), "why didn't you" questions, tag questions ("You knew,
  didn't you?") and rhetorical ones ("Surely you realised?"). At least 12 of them also ask a
  real question in a separate sentence ("You must have known it was dangerous. How many did
  you take?"): label that question's topic, and quote only the challenging sentence in
  confrontational_words.
- 25 reflection turns that must NOT be confrontational: specific, warm reflections that
  start with "you" or name hard circumstances ("You've been carrying all of this on your
  own since the divorce, and it sounds exhausting."), and firm but neutral questions about
  difficult subjects ("Do you ever think about not being here any more?"). Rate their empathy by
  the rules; confrontational: false.
- 20 neighbour turns: pairs of questions, a few turns apart, about two facts that sit close
  together in this case, worded so that one key phrase decides between them. Label each
  with its own fact.
The rest are ordinary turns (greetings, plain questions, summaries, transitions) that carry
the interview along.

VARIETY (checked by the tests)
- No two doctor lines in a file may share their first three words more than four times.
- Do not use these stock openings at all: "Thinking back to", "Before we finish", "I'll pause
  there", "Right, just picking up", "Could we go through", "I'd like to hear about".
- Write as UK psychiatry trainees speak in a seven-minute exam: varied, natural, sometimes
  hesitant; about one turn in six as speech recognition transcribes (lower case, fillers,
  a false start).

THE CHARACTER'S REPLIES
Short and consistent with the case. To a near-miss question the character says they do not
know or that it is not relevant, and never invents an answer, a number, a diagnosis or an
event that is not in the case file. To a confrontational line the character reacts as the
case's affect stages describe (defensive, hurt, closed), adding no new facts. Reveal a fact
only when the doctor has asked about it, and after_rapport facts only after real empathy.

LABELLING RULES (exactly as the runtime applies them)
- topics: the fact ids whose asked_about labels the doctor's line asks the character about,
  judged with the previous exchange. A near miss, a greeting, an explanation, a summary,
  empathy, or a question about something no fact covers is [].
- empathy_words must be copied word for word from a statement in the line, never from a
  question. "specific" needs at least 8 words naming the person's circumstances and
  feelings; stock phrases ("that must be hard") are "brief".
- confrontational_words must be copied word for word from a sentence that is not an
  information-seeking question. Asking for information, even about drinking, self-harm or
  suicide, is never confrontational; statements, "why didn't you..." questions, tag
  questions and rhetorical questions can be.

CHECK BEFORE YOU FINISH
Run: npm run test:api -- -k finetune_data
Fix anything it reports. In your summary give, per case, the number of interviews and turns
and the count of each kind, and list any files you opened by accident.
```

## Prompt G: case files from the station catalogue (coding agent with repository access)

Give this to a coding agent working in this repository, in a **new** session, with one
running order filled in at the end (A, B, C or D). It researches each station's condition
and writes the case files for that running order from
[data/catalogue/stations.yaml](../data/catalogue/stations.yaml). Run it once per running
order; A already has five cases, so it needs eleven. Physical examination stations (B08,
D16) are left out until the simulator supports them. Review every file before committing;
the cases stay `author_draft` and not clinically validated until a clinician has checked
them.

```text
You are writing practice stations for a research prototype that simulates the MRCPsych
CASC exam (PsychiatryEduAI). A trainee psychiatrist interviews a role-played patient,
relative, carer or colleague for seven minutes. Each station is a YAML case file that the
software uses to interpret the trainee's questions, decide which hidden facts may be
revealed, and voice a 3D character who says only what the file contains. Your task is to
write the case files for one running order (a mock exam of 16 stations) from the station
catalogue, researching each condition first so that every station is clinically accurate
and its character is a typical, believable person with that condition.

FILES YOU MAY READ
- data/catalogue/stations.yaml and docs/STATION-CATALOGUE.md (the station definitions)
- data/cases/*.yaml (the existing cases: follow their structure and quality)
- services/api/src/psychiatry_api/cases.py (the case schema: field names and allowed values)
- docs/ADDING-A-STATION.md (how to write each field) and docs/LLM-STATION-PROMPT.md, Prompt A
  only (the authoring rules)
- config/avatar-register.json (3D characters) and config/tts-runtime.json (voices)

FILES YOU MUST NOT OPEN, SEARCH OR GREP
- anything under data/evaluation/, data/sessions/, data/training/, data/finetune/ or artifacts/
- docs/CASC-POC-PLAN.md, docs/REALISM-PLAN.md, docs/PAPER-DRAFT.md, docs/DECISIONS.md,
  docs/QWEN-SPECIFICATION.md, docs/AVATAR-PLAN.md, docs/INTERPRETER-FINETUNE-PLAN.md
They hold held-out test material, results and real transcripts. If you see any of them by
accident, stop and say so in your summary.

STEP 1: RESEARCH EACH STATION BEFORE WRITING IT
For every station in the running order (skip existing cases, which have existing_case set,
and physical examination stations, which have simulator: physical_examination), research
the condition and situation in depth using current, authoritative public sources: ICD-11
clinical descriptions, national clinical guidelines (for example NICE), professional
bodies' public guidance and patient information (for example the Royal College of
Psychiatrists' public pages, the NHS), peer-reviewed reviews, and published accounts of
lived experience. Establish, for this station:
- the typical presentation: core and associated symptoms as the person would describe them
  in their own words, onset, course, severity, and what a clinician would want to elicit;
- who typically has it: realistic age, sex distribution, risk factors, circumstances,
  comorbidity, substance use, social context, so the character is a typical patient rather
  than a textbook list;
- the clinically important specifics for the task: risk factors and protective factors,
  relevant physical health, medication names and plausible doses and side effects,
  investigations, what is normal versus concerning, and the principles of law and ethics
  where relevant (principles only, not a specific jurisdiction's law);
- how such a person, relative or colleague typically reacts in this conversation: their
  worries, misunderstandings, emotions and the questions they ask;
- cultural and social variation that is relevant without being stereotyped.
Rules for research: read for understanding and write everything in your own words. Do not
copy or closely paraphrase any source, quote patient accounts, or save source text to the
repository. Never use exam material: no RCPsych CASC station scripts, past papers, question
banks, revision books, prep-course stations or eLearning. No real patients or public
figures. Record what you relied on as a short "Research basis" list of source titles or
types in the case's author-notes comments (no copied text, no URLs needed).

STEP 2: WRITE EACH CASE
Follow Prompt A's hard rules, output format, fact-writing guidance and checklist, with these
changes and additions:
- Blueprint: skill, subdivision and specialty exactly as in the catalogue entry;
  communication_focus must include the entry's communication emphasis (one or two items).
- Reading time follows the session, not Prompt A's rule: reading_seconds 240 for a morning
  station, 90 for an afternoon one. interview_seconds stays 420.
- The candidate instructions, persona, setting and task must match the catalogue scenario
  and task. The facts must cover the entry's "covers" areas, plus what your research shows a
  good candidate should elicit for this task; 10 to 14 facts, 6 to 9 of them key.
- Persona: a fictional name that suits a modern UK population (vary names across the
  running order, and do not let a name or background stand in for a diagnosis); the age and
  circumstances your research shows are typical; speech_style and affect that sound like a
  real person, not a textbook.
- voice: set sex, age (young, adult, older) and accent en-GB, and speaker: a voice from
  config/tts-runtime.json of the character's sex, matching their age where one is free in
  this running order. The voices' age labels are rough (there is only one older-sounding
  female voice), so if none of the right age is free, choose the closest and say so in your
  summary. The avatar's apparent_age should match; that takes priority over the voice.
- avatar: a character from config/avatar-register.json with the same sex and a fitting
  apparent_age. Use a clothing: medical character for clinician colleagues. A child under 15
  is never role-played: the candidate meets the adult named in the catalogue.
- Within this running order, every case must have a different avatar and a different
  speaker, including the existing cases already in it. Across running orders they may repeat.
  Choose characters' appearance and voice to suit the person, never to signal a diagnosis.
- affect_stages: a starting stage, a stage reached with rapport, and a stage after
  confrontation, each with an expression (neutral, warm, cheerful, sad, tearful, anxious,
  tense, irritable, flat) that fits, and optional hesitations from this list only: "Hmmm.",
  "Mm.", "OK.", "Right.", "Um.", or two joined ("Mm, OK.").
- Add one or two character questions where your research shows such a person would ask
  them, revealing nothing the candidate has not elicited.
- id: a descriptive slug, unique in data/cases/ (for example postnatal-depression-safety-plan).
- Author notes: one comment line per clinical assumption a clinician should check, then
  the Research basis list.

STEP 3: LINK EACH CASE TO THE CATALOGUE
In data/catalogue/stations.yaml, add existing_case: <id> to each station you wrote. Change
nothing else in the catalogue; if a definition looks clinically wrong or unworkable, say so
in your summary instead. Then run npm run catalogue:doc.

CHECK BEFORE YOU FINISH
Run: npm run test:api
It checks each case against the schema and blueprint, that it matches its catalogue slot
and session reading time, and that no avatar or speaker repeats within the running order.
Fix anything it reports. Read every case once more against Prompt A's checklist.

In your summary list, per station: the case id, the character (name, age, avatar, speaker),
the number of facts (key / after_rapport), the research basis, and the clinical assumptions
a clinician should check first. Also list any files you opened by accident.

RUNNING ORDER: <A, B, C or D>
```

## Prompt B2: confirmation set for the catalogue stations (coding agent with repository access)

Step 0 of docs/STUDENT-CROSS-CHECK-PLAN.md. Give this to a coding agent (for example Codex)
in a fresh session. It writes a new held-out set, split `confirmation`, for the 56 catalogue
stations, blind to the question labels, the training lines and the existing evaluation
questions. Review the summary, then commit the files before any cross-check or boundary work.

````text
You are writing a held-out evaluation set for a research prototype in this repository
(PsychiatryEduAI, a simulator of the MRCPsych CASC psychiatry exam). A trainee interviews a
role-played patient, relative or colleague. Software decides which hidden case facts each
trainee line asks about, then reveals them only if allowed. Your questions test that
software once, at the end of an experiment, so they must be written without seeing what
the software was trained or tuned on.

STEP 1: MAKE YOUR INPUTS (run once from the repository root, do not read its source)

  uv run --project services/api --locked python - <<'PY'
  import yaml
  from pathlib import Path
  from psychiatry_api.cases import load_cases
  from psychiatry_api.evaluation.interpreter import SPEECH_CASES
  out = Path("artifacts/confirmation-input"); out.mkdir(parents=True, exist_ok=True)
  ids = []
  for c in sorted(load_cases(), key=lambda c: c.id):
      if c.id in SPEECH_CASES:
          continue
      p = c.persona
      facts = []
      for f in c.facts:
          d = {"id": f.id, "content": f.content, "disclosure": f.disclosure}
          if f.key: d["key"] = True
          facts.append(d)
      doc = {"id": c.id, "title": c.title, "candidate_instructions": c.candidate_instructions,
             "persona": {"role": p.role, "name": p.name, "age": p.age,
                         "description": p.description, "opening_statement": p.opening_statement},
             "facts": facts}
      (out / f"{c.id}.yaml").write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=100))
      ids.append(c.id)
  (out / "ids.txt").write_text("\n".join(ids) + "\n")
  print(len(ids), "stations written to", out)
  PY

It should print 56. Each input holds a station's id, candidate instructions, persona and
facts (id, content, disclosure rule, key flag) and nothing else.

ISOLATION RULES (strict)
You may READ only: this prompt and the files in artifacts/confirmation-input/.
You must NOT open, search, grep or list: data/cases/ (it holds the question labels you must
not see), data/training/, data/finetune/, data/evaluation/ (other than writing your own new
files), data/sessions/, other folders under artifacts/, docs/, prompts/ or the source under
services/ and apps/. The check in step 3 compares your lines with material you have not
seen and reports only your own lines. If you see excluded material by accident, stop and
say so in your summary.

STEP 2: WRITE ONE FILE PER STATION
data/evaluation/interpreter/<id>.confirmation.yaml, for every id in ids.txt:

  # Confirmation set (held out; used once per candidate). Written <date> by <your model and
  # version> from fact contents only, blind to question labels, training lines and other
  # evaluation sets. Not clinically validated.
  case_id: <id>
  split: confirmation
  items:
    - utterance: <one trainee line, as spoken>
      expected: [<fact ids a correct system should select; [] if none>]
      rapport: <true only if the line explicitly expresses empathy or validation>
      previous: {interviewer: <earlier line>, character: <short reply drawn from a fact's content>}   # only for follow-ups

Ten items per station:
- 6 questions that each ask for one fact, on six different facts, key facts first.
- 2 questions on facts whose contents are close to another fact in the same station
  (similar feelings, people, times or worries): word each so a careful reader can tell
  which fact answers it, and label that one fact.
- 1 follow-up that only makes sense after the exchange you give in `previous` (the
  expected fact may differ from the one just discussed).
- 1 line that asks for no fact, choosing one of: an empathic statement (rapport: true),
  a summary, or a plausible clinical question no fact answers, including one that uses a
  fact's obvious words but asks for something the fact does not hold.
Across the 56 stations, use each of those three kinds at least 15 times.

The trainee knows only the candidate instructions, the opening statement, general clinical
knowledge and, in a follow-up, the exchange given. Questions must not contain a fact's
specific details (not "Did your sister find you?" when nothing says a sister exists).
A line asks about a fact when the fact's content answers what is asked, not when it shares
a word. At most two facts per line, and only when the line clearly asks two things (use
this at most five times in the whole set). Use [] rather than guessing.

Write as UK psychiatry trainees speak in a seven-minute station: varied, sometimes
informal, sometimes brief ("and at night?"), about one line in eight as speech
recognition would transcribe it (lower case, a filler). Fit the role: patient, relative,
or colleague (professional discussion). Address the character by name sometimes. Natural
British English; original wording only; no RCPsych material, no real people's names.
Do not modify any other file and do not commit.

STEP 3: CHECK (run from the repository root; fix everything it reports, then run it again)

  uv run --project services/api --locked python - <<'PY'
  import difflib, glob, re, yaml
  from pathlib import Path
  norm = lambda t: " ".join(re.findall(r"[a-z']+", t.lower()))
  ids = Path("artifacts/confirmation-input/ids.txt").read_text().split()
  mine, other = {}, {}
  for path in glob.glob("data/evaluation/interpreter/*.yaml"):
      data = yaml.safe_load(open(path))
      bucket = mine if path.endswith(".confirmation.yaml") else other
      bucket.setdefault(data["case_id"], []).extend(i["utterance"] for i in data["items"])
  for path in glob.glob("data/evaluation/scripts/*.yaml"):
      data = yaml.safe_load(open(path))
      other.setdefault(data["case_id"], []).extend(t["say"] for iv in data["interviews"] for t in iv["turns"])
  for path in glob.glob("data/training/topics/*.yaml") + glob.glob("data/training/tone/*.yaml"):
      data = yaml.safe_load(open(path))
      other.setdefault(data["case_id"], []).extend(i["utterance"] for i in data["items"])
  problems = 0
  for cid in ids:
      case = yaml.safe_load(open(f"artifacts/confirmation-input/{cid}.yaml"))
      facts = {f["id"] for f in case["facts"]}
      path = Path(f"data/evaluation/interpreter/{cid}.confirmation.yaml")
      if not path.exists():
          print("MISSING", cid); problems += 1; continue
      data = yaml.safe_load(path.read_text())
      items = data["items"]
      ok = data["case_id"] == cid and data["split"] == "confirmation" and len(items) == 10
      ok &= all(set(i["expected"]) <= facts and len(i["expected"]) <= 2 for i in items)
      ok &= sum(1 for i in items if i.get("previous")) >= 1
      ok &= sum(1 for i in items if not i["expected"]) >= 1
      if not ok:
          print("SHAPE", cid); problems += 1
      targets = [norm(t) for t in other.get(cid, [])]
      for item in items:
          line = norm(item["utterance"]); m = difflib.SequenceMatcher(None, b=line)
          for t in targets:
              m.set_seq1(t)
              if m.quick_ratio() >= 0.75 and m.ratio() >= 0.75:
                  print("TOO CLOSE to existing material, rewrite:", cid, "|", item["utterance"])
                  problems += 1; break
  print(problems, "problems;", sum(len(v) for v in mine.values()), "items")
  PY

"TOO CLOSE" means your line is nearly identical to a line already in the repository (an
evaluation or training line you have not seen). Rewrite it in different natural words and
rerun; do not go looking for the line it matched.

Finish with a short summary: files written, item counts, how many of each no-fact kind,
lines where you were unsure of the label, and confirmation that you did not open the
excluded files.
````

---

## After the LLM

```sh
npm run test:api                         # schema, blueprint, labels and scripts must all validate
npm run eval:interpreter -- --backend local --split test
npm run eval:fidelity -- --cases <id> --judge none --out artifacts/eval/fidelity-<id>.json
```

Commit the evaluation files before acting on their results. A station drafted by an LLM
is still an author draft: it is not clinically validated, and the author recorded in the
file is the person who reviewed and accepted it, with the model named alongside.
