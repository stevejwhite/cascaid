# Rapport label sets

Written 2026-10-08, before the graded-rapport interpreter (Realism Phase 2) was built or
run. Author-labelled; not reviewed by a clinician. `test.yaml` is held out: do not tune
prompts on it. `development.yaml` may be used for tuning.

Each item labels one trainee utterance:

- `empathy`
  - **0, none:** questions (however gently phrased), greetings, thanks for coming,
    explanations, summaries, neutral acknowledgements ("okay", "I see"), and politeness
    such as "sorry to ask, but...".
  - **1, brief:** a stock or generic expression of sympathy or acknowledgement that could
    follow almost anything: "That sounds hard." "I'm sorry to hear that." "That must be
    difficult." "Thank you for telling me; I know it isn't easy."
  - **2, specific:** names the person's own feeling or situation from what they have said and
    validates it, or reflects it back and invites them to say more: "Losing your job and your
    partner within weeks of each other sounds like it left you feeling there was no way out."
- `confrontational`: challenges, disbelieves, blames, lectures, moralises or pressures,
  including dismissing the person's concerns (clarified after the development run; the
  labels were not changed):
  "You're obviously drinking far too much." "Come on, you must have known what you were
  doing." "Why didn't you just ask for help?"
- `previous`: optional prior exchange, as in the interpreter label sets.

Scored by `npm run eval:rapport`.
