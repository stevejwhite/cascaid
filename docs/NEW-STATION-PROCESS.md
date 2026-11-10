# Adding a new station: the process

The steps, in order, to add a station from first draft to a fully trained station. How to
write each field is in [ADDING-A-STATION.md](ADDING-A-STATION.md); the prompts for an LLM to
draft files are in [LLM-STATION-PROMPT.md](LLM-STATION-PROMPT.md).

**A station works as soon as step 3 passes.** Until it has training data, the language
models decide what each question asks, so replies are a second or two slower. Steps 5 to 7
make it fast. Steps 4 to 7 matter only for a station used in evaluation or regular practice.

| Step | What | Output | Time |
|---|---|---|---|
| 1 | Write the case | `data/cases/<id>.yaml` | hours |
| 2 | Choose its character and voice | fields in the case | minutes |
| 3 | Validate and try it | passing tests; a practice run | 30 min |
| 4 | Write and commit evaluation data **before** any training | `data/evaluation/...` | 1–2 h |
| 5 | Classifier training lines | `data/training/topics`, `data/training/tone` | 1–2 h review |
| 6 | Student interviews (optional) | `data/finetune/synthetic` | 1 h review |
| 7 | Retrain and check | a student run, evaluation results | 2–3 h, mostly unattended |

## 1. Write the case

Copy the existing case closest to yours, or draft one with **Prompt A**. To write the
stations of the [station catalogue](STATION-CATALOGUE.md), use **Prompt G**, one running
order at a time. Follow
[ADDING-A-STATION.md](ADDING-A-STATION.md) for the facts, disclosure rules, affect stages
and tasks. The essentials:

- original fiction only; set the blueprint slot; `clinically_validated: false`;
- every detail the character may say is a fact, with distinctive `asked_about` labels;
- `version: 0.1.0`; keep `authorship.status: author_draft` until you have reviewed it.

## 2. Choose its character and voice

Within a running order of the catalogue (one mock exam) every case has a different 3D
character and voice; they may repeat across running orders. The tests check this, and
that character, voice and `voice.sex` agree. Every case must be in the catalogue.

- **Character:** `persona.avatar`, an `id` from `config/avatar-register.json` (22
  characters, with sex and apparent age; two wear white coats for clinician colleagues). If none
  fits, add a Rocketbox character to the register (pinned by commit and SHA-256, like the
  others), then run `npm run avatars:install`. `/avatar-lab` previews every character with
  each expression.
- **Voice:** `persona.voice.speaker`, one of the 19 American voices in
  `config/tts-runtime.json` (11 female, 8 male), not used by another case in the same
  running order.
- **Expression and hesitations:** give each affect stage an `expression`, and optionally
  `hesitations` (thinking sounds such as `Hmmm.`, used only on slow turns).

## 3. Validate and try it

```sh
npm run test:api        # the case loads, fits the blueprint, has its own character and voice
```

Then run the station at http://127.0.0.1:3105: ask about every fact in your own words, ask
one thing the case does not cover, and try a rapport-gated fact before and after an
empathic remark. Every reply should say only what the facts say. Fix labels, not code.

## 4. Write and commit evaluation data, before any training

So that results stay honest, write these **before** steps 5 to 7, with **Prompt B** in a new
LLM session or by hand, and commit them first:

- `data/evaluation/interpreter/<id>.yaml`: 15–20 labelled questions, `split: test`;
- `data/evaluation/scripts/<id>.yaml`: complete, partial and adversarial interviews.

Each file names `case_id` and the `case_version` it was written for; a test requires the
version to match the case, so a case revision also means reviewing its evaluation files.

Never show these files to whoever writes the training data in steps 5 and 6. The data tests
reject any training line that is a near-copy of an evaluation item.

## 5. Classifier training lines

These make the fast first stage (about 0.06 s) work for the new case.

1. Run **Prompt C** (topic lines) and **Prompt D** (tone lines) with a coding agent, or write
   them yourself. Optionally add a `<id>.conversational.yaml` of openers, introductions and
   name-addressed questions, as the other cases have.
2. Review every file, then set `status: reviewed`. Each file's `case_version` must equal the
   case's `version`.
3. `npm run test:api` (checks labels, the tone rules and near-copies of evaluation items).
4. **Restart the API** (`npm run dev`): the classifiers retrain themselves on the first turn
   after a restart when the training data has changed.

## 6. Student interviews (optional)

The student interpreter reads each case's topics from its prompt, so it already works on a
new station; check it in step 7 before relying on it. To train it on the new case, run
**Prompt E** (whole interviews) and **Prompt F** (near misses, confrontation, neighbouring
facts) for that case only, review the files, and run
`npm run test:api -- -k finetune_data`.

## 7. Retrain and check

```sh
npm run finetune:label                 # Qwen3-4B labels anything the new lines lack (~1 s a line)
npm run finetune:export                # writes artifacts/finetune/data
tools/finetune/train.sh qwen3-0.6b <run>   # about 90 minutes; keep the other servers running
tools/finetune/fuse.sh qwen3-0.6b <run>    # merge and quantise
```

Then compare the new run with the student in use, **in the cascade**, which is what the app
runs:

```sh
npm run student:stop && npm run student:install -- <run> && npm run student:start
STUDENT_BACKEND=local npm run eval:interpreter -- --backend local --split development --interpreter cascade
STUDENT_BACKEND=local npm run eval:interpreter -- --backend local --split test --interpreter cascade
npm run eval:fidelity -- --judge none --out artifacts/eval/fidelity-<run>.json
npm run eval:leaks -- artifacts/eval/fidelity-<run>.json
```

**Adopt the new run only if it releases no more facts wrongly** (spurious selections and
leaks) than the run in use, on both splits and in the fidelity runs. When you adopt it,
copy `artifacts/finetune/data/cases-manifest.json` to `config/model-cases/<model name>.json`
and commit it with the registry change: the status page then reports any case newer than
the model's training set. Topic training files written for another case version are
skipped at runtime (logged), so a revised case uses the model route until they are updated. Otherwise reinstall
the previous run (`npm run student:install -- <previous run>`) and record the result in
[INTERPRETER-FINETUNE-PLAN.md](INTERPRETER-FINETUNE-PLAN.md).

Finally, commit the case, evaluation and training files (never `artifacts/`, which holds
local transcripts and model weights). Run the test split once, at the end: running it again
after changing anything makes its result post hoc.

## When you edit an existing station

- Bump its `version` and update `case_version` in its training files to match; the tests
  fail until they agree.
- If you add, remove or relabel facts, update its evaluation and training files, then
  restart the API (classifiers) and consider retraining the student (step 7).
- Changing a test-split case after seeing its results makes those results post hoc: record
  that in the plan.
