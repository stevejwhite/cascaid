# Avatar prototype plan

Status: agreed 2026-10-13; phase A done, phase B done (route R2), phase C done, phase D done, phase E done, phase F next. Priority: the paper and human testing (blind ratings,
real-voice recordings) are parked until an engaging interactive application has been shown
to be possible.

**Goal:** show that a trainee can hold an engaging spoken conversation with a lifelike
on-screen character, in real time, entirely on this Mac, without changing what the
character knows or the disclosure guarantees.

## Decisions

| Decision | Choice |
|---|---|
| Visual style | A stylised-realistic 3D head rendered in the browser (three.js / WebGL). Photoreal neural "talking photo" video is out of scope: too heavy to run in real time beside Qwen on a 16 GB Mac. |
| Avatar models | Open asset libraries only, with licences that allow use and committing them to the repository. Candidates: Microsoft Rocketbox (MIT) and MakeHuman exports (CC0). Facial blendshapes may need adding in Blender. Licences are confirmed in phase A before any asset is committed. |
| Hands-free conversation | In scope for the first prototype (phase E): turn-taking is a large part of whether conversation feels natural. Click-to-talk stays as a fallback. |

## Starting point

Already in place: local Whisper speech input (click-to-talk), browser read-aloud with a voice
matched to each character, guarded replies released sentence by sentence, per-turn affect
stages and character questions, timing cues, and a median turn of 2.9 s with the classifier
cascade (tag `cascade-1`). Missing: a face, speech-synchronised mouth movement, listening and
thinking behaviour, and hands-free turn-taking.

## Architecture

```
Trainee speaks ─► browser voice detection (end of speech) ─► Whisper ─► API turn (cascade + Qwen)
     ▲                                                                       │ sentences (guarded)
     │  barge-in: speaking stops the character                               ▼
3D head in the browser ◄── behaviour state machine ◄── events: listening / thinking / speaking, affect stage
     ▲                                                                       │
     └── mouth shapes and timings ◄── local neural TTS (audio + word timings) ◄──┘
```

**Rendering.** A 3D head with standard facial blendshapes (ARKit 52 or Oculus visemes), so
expressions and mouth shapes are data, not hand animation. The open-source TalkingHead
library (three.js), built for speech-aligned visemes, blinking, gaze and moods on such
avatars, is evaluated first; its licence and maintenance are checked in phase A. No new
server; the risk to measure is contention with Qwen on the shared Metal GPU.

**Voice.** A local neural text-to-speech model that returns audio with word timings, needed
for lip-sync (browser voices give no access to the audio). Candidate: Kokoro-82M
(Apache-2.0), as a local server like Whisper or in the browser; fallback Piper (voice
licences vary; some are non-commercial and excluded).

**Behaviour.** A deterministic state machine driven by events:

| State | Behaviour |
|---|---|
| Idle | Breathing, blinks, small gaze shifts |
| Listening (trainee speaking) | Eye contact, occasional nods |
| Thinking (end of speech to first audio) | Glances away; in a guarded stage, sometimes an authored hesitation ("mm...") |
| Speaking | Lip-sync and head movement |

The affect stage sets expression and gaze (guarded avoids eye contact, tearful looks sad,
defensive is tense). Each case's affect stages gain an optional `expression` (neutral, sad,
anxious, irritable, cheerful and so on); each persona gains an `avatar`. Neither changes
what the character knows or when facts are released.

**Turn-taking.** Browser voice-activity detection (a small local model such as Silero VAD
in the page) replaces click-to-talk. Barge-in: the trainee starting to speak stops the
character's audio and abandons that reply, and the log records the interruption.

## Latency budget (targets, to be measured)

| Step | Target |
|---|---|
| End of trainee speech detected | at most 0.5 s |
| First visible reaction (thinking behaviour) | at most 0.3 s after end of speech |
| Whisper | about 0.5 s |
| Interpretation and reply (cascade) | about 2–3 s (turn median 2.9 s) |
| First audio of sentence 1 | at most 0.3 s after the sentence is released |
| First word heard | about 3–3.5 s after end of speech |

The immediate thinking behaviour is what makes the wait feel natural. Going much below 3 s to
the first word would need further work (for example a smaller Whisper model, or interpreting
a partial transcript).

## Phases

| Phase | Work | Done when | Effort |
|---|---|---|---|
| A. Spike and decisions | TalkingHead with 2–3 candidate avatars from open libraries; Kokoro measured as a server and in the browser beside Qwen; licences of library, voices and assets; frame rate and Qwen slowdown while rendering | Choices made, with measured speed, frame rate and memory | 2–3 days |
| B. Living face | Avatar in the station page: idle, listening, thinking and speaking states from existing events; browser voice with approximate mouth movement | Station runs with a face that reacts immediately | 2–3 days |
| C. Real voice and lip-sync | Local neural TTS with word timings; synthesis sentence by sentence as guarded sentences arrive; viseme lip-sync; voice per character | Lips match speech; time to first audio measured | 3–4 days |
| D. Character | Affect stage to expression and gaze; one avatar per case; authored hesitations | Each character looks and sounds distinct; affect changes are visible | 2–3 days |
| E. Hands-free conversation | Voice-activity detection for end of speech; barge-in cancels the reply; click-to-talk fallback | Natural back-and-forth without clicking; barge-in within 300 ms | 2–3 days |
| F. Measure and judge | Latency budget, frame rate under load, memory with all servers, a recorded demo of each station; your judgement of engagement against the current text and voice version | Go or no-go on the avatar route, with numbers | 1–2 days |

About 2.5–3.5 weeks. This replaces Realism Phase 3's neural voices, end-of-speech detection
and interruption work ([REALISM-PLAN.md](REALISM-PLAN.md)); linked stations remain separate.

## Phase A results (in progress, 2026-10-13)

Measured on the Apple M4 with Qwen3-4B and the embedding server running. Spike code is kept
outside the repository; nothing is installed in the app yet.

**Components and licences**

| Component | Version | Licence | Finding |
|---|---|---|---|
| TalkingHead (three.js avatar class) | 1.7.0 | MIT | Speech-aligned visemes from audio with word and viseme timings; moods, gaze, eye contact, blinking; built-in voice-activity events |
| three.js | 0.180.0 (TalkingHead's dependency) | MIT | |
| HeadTTS (Kokoro-82M, ONNX, timestamped) | commit `c08f4ca` | MIT; Kokoro weights Apache-2.0 | Local Node server; returns audio with word timings and Oculus visemes; no eSpeak (no GPL) |
| Microsoft Rocketbox avatars | archived repository, October 2026 | MIT | 115 rigged characters; Female_Adult_01 has 175 blendshapes including all 15 Oculus visemes and all 52 ARKit shapes |
| Silero-based voice-activity detection (`@ricky0123/vad-web`) | 0.0.31 | ISC | Not yet tested (phase E) |

**Measurements**

| Measure | Result |
|---|---|
| Kokoro synthesis, Qwen idle | median 0.38 s per sentence (2.5–8 s of speech), real-time factor 0.14 |
| Kokoro and Qwen at the same time | Qwen 0.72 s to 1.72 s per call; Kokoro 0.72 s to 1.04 s. **Design rule: never synthesise while Qwen generates** (natural in a turn: synthesis follows the guarded reply; on barge-in, cancel synthesis) |
| HeadTTS server memory | 1.2 GB resident (four servers together about 6.3 GB) |
| Avatar rendering (headless Chromium, ANGLE Metal on the M4) | 48–60 frames per second idle and while speaking with lip-sync |
| Qwen while the avatar renders | 0.68 s per call with and without rendering; avatar held 60 fps during generation |

**Findings that change the plan**

- **Accent.** HeadTTS phonemises with an American English dictionary only, so Kokoro's British
  voices would speak with American pronunciation. Options: accept American voices for the
  prototype; add a British pronunciation dictionary to HeadTTS; or use kokoro-js, whose
  phonemizer bundles eSpeak NG (GPL-3.0, to be checked before use).
- **Avatar conversion needs Blender.** Rocketbox characters carry the right blendshapes, and
  renaming them is trivial (done in a browser-based converter). But they use a 3ds Max Biped
  skeleton in centimetres with several materials, while TalkingHead expects a Mixamo-style
  skeleton in metres. A browser-only conversion gave a valid model of the right size with
  scrambled materials, and TalkingHead could not pose it. TalkingHead's author provides
  Blender scripts for Rocketbox models; a scripted, unattended Blender pipeline (import,
  apply scale, rename bones and shape keys, rebuild materials, keep only the 67 blendshapes
  used, compress, export GLB) is the reliable route.

**Update, later on 2026-10-13.** Blender 4.5.14 LTS was installed (official image, checksum
and code signature verified). Its FBX importer reads Rocketbox materials correctly, giving a
believable, correctly textured face in a plain three.js viewer (25 MB GLB with all 175
blendshapes). Making that model drivable by TalkingHead failed within the time-box:
TalkingHead sets absolute bone rotations tuned to a Mixamo-style skeleton (axes, rest pose,
hierarchy with legs under the hips), and a browser-side re-orientation of the Rocketbox
Biped skeleton fixed the axes, root and proportions but not the mesh binding, so nothing
rendered. Two ways forward:

| Route | What | Cost and risk |
|---|---|---|
| R1. Retarget in Blender | Scripted Blender pipeline: rebuild the skeleton in Mixamo convention, re-parent (legs under hips, shoulders under upper spine), rebind the mesh with its shape keys, then use TalkingHead as is (gestures, body poses, moods) | 1–2 days; skeleton surgery with shape keys is fiddly; every Rocketbox character goes through it |
| R2. Drive Rocketbox natively | Keep the Blender-exported model as it is; a small three.js driver applies HeadTTS visemes and ARKit expressions to the blendshapes, blinks, moves the eyes (blendshapes) and makes small head, neck and breathing movements relative to the rest pose; seated head-and-shoulders framing | 1–2 days; no retargeting at all; loses TalkingHead's gestures and body poses, which a seated head-and-shoulders view barely shows |

Recommendation: R2 for the prototype. A seated consultation shows head and shoulders, where
the face, eyes and lip-sync carry the realism, and R2 avoids the riskiest step entirely.
R1 stays an option if body language proves important.

## Phase B results (2026-10-13): route R2, the living face

- **Asset pipeline.** `config/avatar-register.json` pins two Rocketbox characters
  (Female_Adult_01, Male_Adult_08) by commit `0943055` and SHA-256 per file, with the MIT
  licence. `npm run avatars:install` downloads and verifies them, then converts each with
  Blender 4.5.14 run unattended (`scripts/avatars/convert.py`): textures re-linked and
  shrunk to 1024 px, only the 15 Oculus visemes and 52 ARKit blendshapes kept, under their
  standard names. Output (about 10–11 MB per character, with the licence) goes to
  `apps/web/public/avatars/`, which is not committed. The installer fails if any texture or
  blendshape is missing.
- **Driver.** `lib/avatar/behaviour.ts` (states idle, listening, thinking, speaking;
  blinks every 2–6 s; gaze and eye contact per state; slow head drift; listening nods;
  breathing; mood baselines; damped under reduced motion), `lib/avatar/lipsync.ts`
  (approximate visemes from word-boundary events of the browser voice) and
  `components/avatar-view.tsx` (three.js 0.180.0; joint movements applied as world-space
  rotations about each joint's rest pose, so the Biped skeleton needs no retargeting;
  arms lowered from the A-pose; head-and-shoulders framing from eye level).
- **Station.** "Show the character (3D, experimental)", remembered per browser. Recording
  or typing makes the character listen; transcription and waiting for the reply make it
  think (head tilt, gaze away); read-aloud makes it speak. The character follows the case's
  voice hint until phase D assigns one per case. `/avatar-lab` is a development page for
  states, moods and a silent mouth test.
- **Measured:** 60 frames per second in the station page (headless Chromium on the M4),
  idle and during speech; a real turn with Qwen and the cascade completed normally.
- **Tests:** 9 new web tests (visemes, cross-fades, blink rate, gaze, moods, reduced motion,
  speech events, state mapping, the station option); 33 web tests in all.
- **Known limits:** the mouth follows estimated word timings from the browser voice, not the
  audio (phase C); headless Chromium has no voices, so spoken lip-sync was checked only with
  the silent test; the alcohol case's Chris is shown by the female character until phase D.

## Phase C results (2026-10-13): the character's voice and lip-sync

- **Runtime.** `config/tts-runtime.json` pins HeadTTS at commit `c08f4ca` (MIT, source
  tarball by SHA-256; dependencies from its lockfile, install scripts not run) and
  Kokoro-82M-v1.0-ONNX-timestamped at revision `dd4401a` (Apache-2.0; every model file and
  six American voices by SHA-256). `npm run tts:install` / `tts:start` / `tts:stop`. The
  server is bound to 127.0.0.1:8183 (a preload forces loopback), serves REST only with no
  CORS, and loads the model from the verified files with remote downloads disabled. WebGPU
  (Metal) was about 30% faster than CPU per sentence, so it is the default. Cold start 1.8 s;
  1.5 GB resident.
- **API.** `POST /api/sessions/{id}/speech` voices one sentence through a
  `Synthesizer` adapter (`psychiatry_api/synthesis.py`; `TTS_BACKEND=off|fake|local`). It
  voices only text the character has already said in that session, after the disclosure
  gates and output guard, so the voice cannot add anything. It waits for a turn in progress
  to be saved and holds the same generation slot as Qwen and Whisper, so **synthesis never
  runs while Qwen generates** (the phase A design rule, enforced in code and tested). Audio
  is returned, never stored. `/api/status` reports the voice.
- **Browser.** `lib/neural-voice.ts` requests each released sentence as soon as it arrives,
  plays the sentences strictly in order through WebAudio, skips Kokoro's ~0.45 s leading
  silence, and sends Kokoro's own viseme timings to the avatar (replacing estimates).
  Sending a turn, speaking, or turning read-aloud off stops the voice at once and cancels
  pending synthesis (the basis of barge-in in phase E). Voices follow the presented sex and
  age (`af_heart`/`af_bella`/`af_sarah`, `am_puck`/`am_michael`/`am_fenrir`), with a per-case
  override; the browser voice remains the fallback when the service is not ready or fails.
  The station shows "Reply audible after N s" for each reply.
- **Measured** (`npm run eval:voice`, 5 cases × 3 generic questions, cascade interpreter,
  M4): time from sending a turn to the first audio ready to play, median **3.8 s** (max
  6.0 s), of which the first guarded sentence takes a median 3.3 s and its synthesis about
  0.4 s; synthesis real-time factor 0.16; **no silent gaps** between sentences in any turn.
  In the browser, a cascade-routed turn was audible after 1.4 s. Results:
  `artifacts/eval/voice.json`.
- **Tests:** 8 API tests (only the character's own lines, known voices, loopback only,
  failures, readiness, waiting for the generation slot, nothing stored); 6 web tests
  (voice choice, silence trimming and cue timing, in-order playback, stop and cancel,
  failure fallback, the station using the character voice instead of the browser's).
- **Known limits:** American accent only (HeadTTS's dictionary); the whole reply is still
  generated before the first sentence is released, so time to first audio is dominated by
  generation; lip-sync timing was checked by screenshots, not by ear, in headless runs.

## Phase D results (2026-10-13): one character per case, with visible affect

- **One character and voice per case** (cases 0.4.0; presentation only, so facts and
  disclosure are unchanged and the training data still applies). Five more Rocketbox
  characters are registered and converted, chosen for age and spread of appearance; each
  persona names its `avatar`, and its voice hint names its Kokoro `speaker`:

  | Case | Character | Rocketbox | Voice |
  |---|---|---|---|
  | Chris, 46, alcohol | man | Male_Adult_12 | am_michael |
  | Alex, 28, elevated mood | young man | Male_Adult_06 | am_puck |
  | Jordan, 34, overdose | woman | Female_Adult_11 | af_heart |
  | Helen, 52, memory (collateral) | woman | Female_Adult_14 | af_bella |
  | Maria, 55, clozapine (relative) | older woman | Female_Adult_02 | af_sarah |

  Chris, Alex and Jordan had no stated sex; nothing in their cases refers to their own
  gender, so presenting one changes no fact. A test requires every case to have its own
  registered character and installed voice, consistent with its voice hint.
- **Affect to expression.** Each affect stage has an `expression` (neutral, warm, cheerful,
  sad, tearful, anxious, tense, irritable, flat). The session view reports the expression of
  the stage behind the latest reply. Each expression sets ARKit blendshapes and a bearing:
  how much eye contact is kept, how far the head is lowered, how lively it moves (a flat,
  guarded character looks down and away; tearful brows lift; tense lips press). Changes ease
  in over about a second. Seen in the station: Jordan starts flat; after an empathic line
  the stage moved to opening-up and the face to tearful.
- **Authored hesitations.** A stage may list up to four fillers from a closed vocabulary
  ("Mm.", "Well...", "I...", "Sorry..."), validated so they can carry no fact, number or
  name. They are synthesised ahead while the character is idle (the speech endpoint accepts
  only the case's authored fillers besides its own lines), and on every other turn one plays
  if the reply has not started 0.9 s after sending. They are not logged and do not count as
  the reply's first audio. Seen in the station: "Mm." at 0.93 s, the reply at 3.7 s.
- **Rendering fix.** The FBX import had made every material fully metallic, which rendered
  skin dark and patchy (darker skin worst, and a pale band across one face). The converter
  now sets Metallic to 0 and the installer checks it. (The normal maps were checked and are
  already in the OpenGL convention three.js expects.)
- **Tests:** 13 API tests (registered characters and voices, one per case, filler
  vocabulary, presentation per stage, which fillers may be voiced); 7 web tests (easing,
  bearing, every expression defined, rotation of fillers, prepared audio not counted as the
  reply, the case's character, expression and voice in the station, a filler before a slow
  reply). 176 API and 46 web tests in all.
- **Known limits:** expressions were judged by eye from renders, not rated; the five
  characters were chosen by the developer for this prototype and are data that can be
  changed; fillers are American-accented like the voices.

### Revision after use: hesitations (2026-10-13)

In use, the hesitations were odd and distracting: several were sentence openings ("I...",
"Sorry...", "Look...") followed by a different sentence, and they came 0.9 s after sending
whatever the wait. Now:

- **Thinking sounds only**, from a closed list: "Hmmm.", "Mm.", "OK.", "Right.", "Um."
  (Kokoro says "Hmmm." as a closed-mouth hum; "Hm." and "Uh-huh." sounded wrong and are
  excluded). Each stage picks a subset; a flat character only says "Mm.".
- **Only on slow turns.** Interpreters gained a `forecast`: the cascade reuses the
  classifier rating it needs anyway to say whether the turn will wait for Qwen; the
  streaming turn sends `{type: pace, slow}` before anything else. Fast turns get no sound,
  only the glance away.
- **Midway, quieter, not twice running.** On a slow turn the sound comes 1.8 s after
  sending (with end-of-speech detection and transcription before that, about midway
  through a 7–8 s wait), at 70% volume, and never on two slow turns in a row.
- Seen in the station (alcohol case, five questions): slow turn: "Hmmm." at 1.8 s, reply at
  6.3 s; three fast turns: no sound, replies at 2.0–2.7 s; a second slow turn: no sound.

## Phase E results (2026-10-13): hands-free conversation and interruptions

- **Voice-activity detection in the page.** Silero VAD v5 (MIT) through
  `@ricky0123/vad-web` 0.0.31 (ISC, exact pin) and onnxruntime-web 1.30.0 (MIT, lockfile).
  The model, worklet and WebAssembly runtime are copied from those packages into
  `apps/web/public/vad` (not committed) by `predev`/`prebuild`, with a checksum manifest,
  and served by the app: no CDN. One thread; the audio stays in the page and goes only to
  the local API for transcription, as before.
- **Hands-free option** ("Hands-free conversation (headphones recommended)", remembered;
  offered when speech recognition is ready). Speech ends after 600 ms of silence and is
  transcribed and sent without clicking. Click-to-talk remains when the option is off.
  Words spoken while a reply is still in flight are sent as soon as it lands.
- **Interruptions.** When possible speech starts while the character's voice plays (or is
  about to), the voice drops to 20% at once; after 250 ms of confirmed speech it stops and
  pending synthesis is cancelled; a false start restores the volume. Speaking while the
  reply is still being prepared means that reply is shown but not read aloud. Each
  interruption is logged (`interrupted`: after which turn, speaking or thinking, how many
  ms were heard) and the debrief says how often the trainee spoke over the character.
  Nothing the character said is removed from the transcript.
- **Echo.** Detection is stricter while the character speaks, and speech that began during
  playback is discarded if at least 80% of its words (three or more) are in the
  character's line, so its own voice through speakers is not taken as the trainee. Speech
  that began after the character finished is never filtered, so reflections and summaries
  are always sent. Headphones remain the recommendation.
- **Fixed on the way:** cancelled synthesis was reported as a failure (switching the
  character to a browser voice after an interruption); a voice that ended while ducked
  stayed quiet.
- **Measured** (`npm run eval:hands-free`: headless Chromium with a synthetic microphone,
  macOS `say` as the trainee, 5 cases × 2 questions, the second timed to land on the reply):
  all 10 utterances heard and sent verbatim; end of speech detected 0.38 s (median) after
  the VAD's speech end, about 0.5 s after the true end; the character's voice ducked as soon
  as speech was detected (about 0.1 s after onset) and stopped 0.35 s after detection
  (4 interruptions); transcription 1.04 s; reply audible a median 4.9 s after end of speech
  was detected. Results: `artifacts/eval/hands-free.json`.
- **Against the budget:** end-of-speech detection meets 0.5 s; the audible yield meets
  0.3 s but the full stop (0.35 s after detection) does not; Whisper large-v3-turbo takes
  about 1 s rather than 0.5 s; and these generic questions mostly took the Qwen route, so
  the first word came about 5 s after the trainee stopped, not 3–3.5 s. Next levers:
  a smaller Whisper model, and keeping more turns on the classifier route.
- **Tests:** 2 API tests (interruptions logged, counted, validated; transcript unchanged);
  6 web tests (hands-free send without clicking, interrupting speech and preparation, echo
  discarded, echo rule, cancelled synthesis not a failure). 178 API and 52 web tests.
- **Known limits:** echo handling was not tested with real speakers (the synthetic
  microphone hears no playback); the VAD settings were chosen, not tuned on real trainees.

## Speed improvements (2026-10-13)

**Smaller Whisper.** `npm run eval:asr` (570 synthetic utterances, six macOS voices):

| Model | WER | Exact transcripts | Mean time per utterance |
|---|---|---|---|
| large-v3-turbo Q5_0 (previous default) | 0.11% | 97.0% | 985 ms |
| **small.en (new default)** | 0.15% | 98.9% | **223 ms** |
| base.en | 1.22% | 93.9% | 78 ms |

With small.en, interpretation of the spoken utterances (Daniel voice, 95 items) matched the
labels as often as with turbo (96.8% vs 95.8%) and agreed with typed input on 94 of 95.
Synthetic voices are clean, so this must be re-checked on real (accented) speech; the turbo
model stays one flag away (`npm run speech:start -- --model ggml-large-v3-turbo-q5_0.bin`).

**More conversational training lines.** Logged sessions showed the classifiers decided only
15% of real trainee lines (`npm run eval:coverage`): real lines greet, address the
character by name, add preambles ("Okay, I just need to go over a few things…") and ask
generic openers. 196 new lines, in separate `*.conversational.yaml` files marked as drafts
(written by Claude, not yet reviewed): openers, introductions and transitions with no topic,
and name-addressed or prefaced questions for each fact, including introductions that end in
a real question (without those, a long greeting plus question was wrongly taken as no
topic). Lines were rephrased until none was a near-copy of an evaluation item or a logged
session line. Results:

- Logged real lines decided by the classifiers: 15% → 22% (88 lines). Most of the rest
  are context-dependent ("How long has this been going on?"), two questions in one turn, or
  long multi-part turns, which correctly go to Qwen.
- Development split: classifier decides 15 → 18 of 27 lines, all exact, none spurious;
  cascade exact 25/27 and spurious 2 unchanged. Out-of-fold coverage 31% → 37% at 99.1%
  exact.
- Two logged lines now differ from Qwen's label, both defensible (Qwen labelled a question
  about a liver blood test as drinking duration).

**End to end** (`npm run eval:hands-free`, same 10 utterances): transcription 1.04 s →
0.32 s (including upload); reply audible after end of speech, median 4.9 s → 4.4 s. Almost
all of the gain is Whisper; the test's generic opener still mostly goes to Qwen. The
remaining wait is dominated by the Qwen route, so the next lever is the reply itself
(streaming the first sentence, or a faster interpretation of generic and contextual lines).

## Constraints carried over

- Everything runs on this machine: rendering, speech recognition and speech synthesis
  ([AGENTS.md](../AGENTS.md), rule 5). No audio is stored.
- The case remains the only source of what the character knows; the avatar adds nothing the
  character could reveal.
- New models and assets are pinned by revision and checksum, with licences recorded.
- Every claim about latency, frame rate or memory comes from a reproducible measurement.
