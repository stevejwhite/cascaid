# Getting started

How to install, start, stop and restart the CASC simulator on this Mac, and what to check
when something is not working. Everything runs locally; nothing is sent to a hosted service.

The cases are fiction and **not clinically validated**; feedback is not a CASC mark.

## What runs

The application is up to seven local processes. You start them with up to five commands, each in its own
terminal window, and leave them running.

| Command | What it starts | Port | Needed for |
|---|---|---|---|
| `npm run models:start` | Qwen3-4B (the character) and Qwen3-Embedding (the fast classifiers) | 8180, 8181 | Real replies (`MODEL_BACKEND=local`) |
| `npm run speech:start` | Whisper small.en (speech recognition) | 8182 | Speaking instead of typing |
| `npm run tts:start` | Kokoro-82M (the character's voice) | 8183 | The character's own voice and lip-sync |
| `npm run student:start` | The fine-tuned student interpreter (optional) | 8184 | Faster replies (`STUDENT_BACKEND=local`) |
| `npm run dev` | The API and the web app | 8105, 3105 | Always |

Speech recognition uses Whisper small.en by default (about 0.2 s per utterance). If it
mishears your accent, try the larger model, which is about four times slower:
`npm run speech:install -- --models ggml-large-v3-turbo-q5_0.bin` once, then
`npm run speech:start -- --model ggml-large-v3-turbo-q5_0.bin`.

Only `npm run dev` is essential. Without the others the app still works: typing instead of
speaking, a browser voice instead of the character's, or (with `MODEL_BACKEND=fake`)
scripted stand-in replies.

All servers listen on 127.0.0.1 only.

The student interpreter is a small model fine-tuned on this machine
([INTERPRETER-FINETUNE-PLAN.md](INTERPRETER-FINETUNE-PLAN.md)). Its weights are not in the
repository (they were trained partly on your own local sessions), so it is available only
where it was trained: `npm run student:install -- <run>` once, after training. Without it,
Qwen does its job and replies are a little slower.

## Before the first start (once)

You need Node 22 or newer, npm and uv. The model servers need an Apple Silicon Mac.

```sh
npm run models:install    # Qwen models, ~3.1 GB, checksum-verified
npm run speech:install    # builds whisper.cpp with Metal (~1 min) and downloads Whisper small.en (~0.5 GB)
npm run tts:install       # HeadTTS and Kokoro-82M with six voices (~0.33 GB)
npm run avatars:install   # the 3D characters; needs Blender 4.5.14 in /Applications
```

The first `npm run dev` creates `.env` from `.env.example`. To use everything, set these in
`.env` (the older name `QA_BACKEND` works in place of `MODEL_BACKEND`):

```sh
MODEL_BACKEND=local
SPEECH_BACKEND=local
TTS_BACKEND=local
```

## Start

Open four terminal windows in the repository folder and run one command in each, in this
order. Wait for each "ready" message before starting the next.

```sh
npm run models:start     # "generation ready on 8180" and "embedding ready on 8181"
npm run speech:start     # "Speech recognition ready on 8182"
npm run tts:start        # "Speech synthesis ready on 8183"
npm run student:start    # optional: "Student interpreter ready on 8184"
npm run dev              # "Web: http://127.0.0.1:3105 | API: http://127.0.0.1:8105/docs"
```

Then open **http://127.0.0.1:3105**. The status cards at the top of the station list
should all say ready: station cases, source registry, generation, speech recognition and
character voice.

Run these yourself in your own terminals. Servers started by Claude Code (or any other
tool) stop when that session ends, which shows up later as "Speech recognition
unavailable" or a station that cannot reply.

The first reply after starting the API takes several seconds longer than usual, because the
classifiers load on first use. After that a reply is usually audible within 3 to 5 seconds.

## Run a station

1. Click **Start station** on a case, read the candidate instructions, and click **Begin
   interview now** (or wait for the reading time to run out).
2. Type, or use the microphone:
   - **Speak to …**: click to talk, click again to stop; the words appear for you to
     check before sending (or tick *Send speech without reviewing*).
   - **Hands-free conversation**: just talk. What you say is sent when you pause, and
     speaking over the character stops it. Use headphones, so the microphone does not hear
     the character.
3. Options under the text box, remembered by your browser:
   - **Show the character (3D, experimental)**: the case's character, whose expression
     follows how it feels.
   - **Read replies aloud**: in the character's own voice when speech synthesis is running,
     otherwise a browser voice. A *Voice* menu overrides the choice for that case.
   - **Announce time cues**: the one-minute warning and "Time is up".
4. Click **End station** (or let the time run out) for the debrief.

The browser asks for microphone permission the first time.

## Stop

Press **Ctrl-C** in each terminal. Or, from any terminal in the repository folder:

```sh
npm run dev:stop
npm run student:stop
npm run tts:stop
npm run speech:stop
npm run models:stop
```

Each stop command only stops this project's own server, and says so if it was not running.

## Restart

**Everything:** stop all four, then start them again in the order above.

```sh
npm run dev:stop; npm run student:stop; npm run tts:stop; npm run speech:stop; npm run models:stop
# then, in four terminals:
npm run models:start
npm run speech:start
npm run tts:start
npm run student:start    # optional
npm run dev
```

**Only what changed.** Most changes need less than a full restart:

| You changed or noticed | Do this |
|---|---|
| A case file in `data/cases/` | Nothing: cases are read when a station starts. Start a new station. |
| API code in `services/api/src/` | Nothing: `npm run dev` reloads the API itself. |
| Web code in `apps/web/` | Nothing: the page reloads itself. |
| `.env` | Restart `npm run dev` (Ctrl-C, then `npm run dev`). |
| A status card says *unavailable* | Restart that server (see the table under "What runs"). |
| After `models:install`, `speech:install` or `tts:install` | Restart that server. |
| After `avatars:install` | Reload the page. |
| After `npm install` or a new dependency | Restart `npm run dev`. |

A station that is already running keeps the case version it started with; start a new
station to see case changes.

## When something is wrong

| Symptom | Likely cause and fix |
|---|---|
| *Speech recognition: unavailable* | Whisper is not running: `npm run speech:start`. |
| *Character voice: unavailable*, or replies in a robotic voice | Kokoro is not running: `npm run tts:start` (and `TTS_BACKEND=local` in `.env`). |
| "The simulated character could not reply" | Qwen is not running: `npm run models:start`. |
| "Port … is in use" | An earlier copy is still running: use the matching stop command, then start again. |
| "Character not installed" in the 3D view | `npm run avatars:install`. |
| Hands-free never hears you | Check the browser's microphone permission for 127.0.0.1:3105; turn hands-free off to use click-to-talk. |
| Hands-free reacts to the character's own voice | Use headphones. |
| The first reply is slow | Normal after a restart: the classifiers load on the first turn. |
| VS Code: "terminal environment injection is disabled" | Ignore it or click "Don't show again". The app reads `.env` itself. Turning injection on would leak `.env` settings into `npm test`. |

Server logs are in `artifacts/m4/`: `generation-runtime.log`, `embedding-runtime.log`,
`speech-runtime.log`, `tts-runtime.log` and `student-runtime.log`. Readiness is also at http://127.0.0.1:8105/api/status.

## Checks and measurements

```sh
npm test                                                  # API and web unit tests
npm run eval:voice -- --out artifacts/eval/voice.json     # time to first audio (all servers running)
npm run eval:hands-free -- --out artifacts/eval/hands-free.json   # hands-free conversation in a headless browser
```

See the [README](../README.md) for the full list and [AVATAR-PLAN.md](AVATAR-PLAN.md) for
how the character was built and measured.
