"use client";

import { type FormEvent, type KeyboardEvent, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import {
  ApiError, beginInterview, endSession, recordInterruption, sendTurnStream, startSession, synthesize,
  type Debrief, type SessionView, type SpeechView, type TranscriptionView,
} from "../lib/api";
import { onVoicesChanged, speak, startRecording, stopSpeaking, voiceNames, type StartRecording } from "../lib/recorder";
import { pickVoice, type VoiceLike } from "../lib/voices";
import {
  characterVoice, HESITATE_AFTER_MS, HESITATION_VOLUME, hesitationFor, KOKORO_NAMES, NeuralSpeaker, WebAudioOut,
} from "../lib/neural-voice";
import { label } from "./stations";
import { StationTitle } from "./station-title";
import { DebriefView } from "./debrief";
import { store, stored, storedText, VoiceInput, type VoicePhase } from "./voice";
import { HandsFree } from "./hands-free";
import { isEcho, startListening, type StartListening } from "../lib/hands-free";
import { onSpeech } from "../lib/avatar/speech";
import dynamic from "next/dynamic";
import type { AvatarState } from "../lib/avatar/behaviour";

// WebGL runs in the browser only; the 3D character loads when the trainee turns it on.
const AvatarView = dynamic(() => import("./avatar-view"), { ssr: false });

/** How the character presents: the case's voice hint, or a stable choice from the case id. */
export function presentedSex(caseId: string, sex: string | null | undefined): "female" | "male" {
  if (sex === "female" || sex === "male") return sex;
  const hash = [...caseId].reduce((h, c) => (h * 31 + c.charCodeAt(0)) >>> 0, 7);
  return hash % 2 ? "male" : "female";
}

/** Fallback when a case names no character: one per presented sex. */
export function avatarFor(caseId: string, sex: string | null | undefined): string {
  return presentedSex(caseId, sex) === "female" ? "female-adult-01" : "male-adult-08";
}

export function clock(seconds: number): string {
  const s = Math.max(0, Math.ceil(seconds));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** Seconds remaining until `until`; calls `onExpire` once, from the timer, at zero. */
function useCountdown(until: number | null, onExpire: () => void): number | null {
  const [now, setNow] = useState(() => Date.now());
  const expire = useRef(onExpire);
  useEffect(() => { expire.current = onExpire; });
  useEffect(() => {
    if (until === null) return;
    let fired = false;
    const timer = setInterval(() => {
      const current = Date.now();
      setNow(current);
      if (!fired && current >= until) { fired = true; expire.current(); }
    }, 250);
    return () => clearInterval(timer);
  }, [until]);
  return until === null ? null : (until - now) / 1000;
}

/** Lines within this distance of the bottom count as "following the conversation". */
const FOLLOW_PX = 80;

function Transcript({ session, pending, reply = [] }: { session: SessionView; pending?: string; reply?: string[] }) {
  const box = useRef<HTMLOListElement | null>(null);
  // Follow new lines unless the trainee has scrolled up to reread; sending a line or
  // returning to the bottom resumes following.
  const following = useRef(true);
  const onScroll = () => {
    const el = box.current;
    if (el) following.current = el.scrollHeight - el.scrollTop - el.clientHeight < FOLLOW_PX;
  };
  useEffect(() => { if (pending) following.current = true; }, [pending]);
  const last = session.transcript[session.transcript.length - 1]?.text;
  useLayoutEffect(() => {
    const el = box.current;
    if (el && following.current) el.scrollTop = el.scrollHeight;
  }, [session.transcript.length, last, pending, reply.length]);
  return <ol className="transcript" aria-label="Transcript" aria-live="polite" ref={box} onScroll={onScroll} tabIndex={0}>
    {session.transcript.map((line, index) =>
      <li key={index} className={line.speaker}>
        <strong>{line.speaker === "candidate" ? "You" : session.character_name}</strong>
        <p>{line.text}</p>
      </li>)}
    {pending && <li className="candidate"><strong>You</strong><p>{pending}</p></li>}
    {pending && <li className={reply.length ? "character" : "character waiting"}>
      <strong>{session.character_name}</strong><p>{reply.length ? reply.join(" ") : "…"}</p></li>}
  </ol>;
}

interface RunnerProps {
  caseId: string;
  onExit: () => void;
  /** Offer microphone input (the API's speech backend is not "off"). */
  speech?: boolean;
  /** Read replies in the character's neural voice (local speech synthesis is ready). */
  neural?: boolean;
  record?: StartRecording;
  /** Voice-activity detection for hands-free conversation (replaced in tests). */
  listen?: StartListening;
}

/** What the character is doing, from what the trainee and the station are doing. */
export function avatarState(pending: string | undefined, mic: VoicePhase, draft: string): AvatarState {
  if (pending || mic === "transcribing") return "thinking";
  if (mic === "recording" || mic === "starting" || draft.trim()) return "listening";
  return "idle";
}

export function StationRunner({ caseId, onExit, speech = false, neural = false, record = startRecording, listen = startListening }: RunnerProps) {
  const [session, setSession] = useState<SessionView | null>(null);
  const [debrief, setDebrief] = useState<Debrief | null>(null);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState<string | undefined>();
  const [reply, setReply] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [transcriptionId, setTranscriptionId] = useState<string | null>(null);
  const [autoSend, setAutoSend] = useState(() => stored("casc.autoSend", false));
  const [speakReplies, setSpeakReplies] = useState(() => stored("casc.speakReplies", false));
  const [showAvatar, setShowAvatar] = useState(() => stored("casc.showAvatar", true));
  const [micPhase, setMicPhase] = useState<VoicePhase>("idle");
  const [handsFree, setHandsFree] = useState(() => stored("casc.handsFree", false));
  // Whether the character's voice is playing, and since when (for interruptions).
  const [characterSpeaking, setCharacterSpeaking] = useState(false);
  const speakingSince = useRef(0);
  useEffect(() => onSpeech((event) => {
    if (event.type === "start") { speakingSince.current = performance.now(); setCharacterSpeaking(true); }
    else if (event.type === "end") setCharacterSpeaking(false);
  }), []);
  // Set when the trainee talks over a reply still being prepared: it is not read aloud.
  const silenced = useRef(false);
  // Speech transcribed while a reply is in flight, sent as soon as it lands.
  const queued = useRef<{ text: string; id: string | null } | null>(null);
  const [spokenCues, setSpokenCues] = useState(() => stored("casc.spokenCues", false));
  const voiceSnapshot = useSyncExternalStore(onVoicesChanged, voiceNames, () => "");
  const voices = useMemo<VoiceLike[]>(() => voiceSnapshot.split("\n").filter(Boolean)
    .map((row) => { const [name, lang] = row.split("\t"); return { name, lang, localService: true }; }), [voiceSnapshot]);
  const voiceAvailable = voices.length > 0;
  const [voiceOverride, setVoiceOverride] = useState(() => storedText(`casc.voice.${caseId}`));
  const [kokoroOverride, setKokoroOverride] = useState(() => storedText(`casc.kokoro.${caseId}`));
  const [neuralFailed, setNeuralFailed] = useState(false);
  const [firstAudioMs, setFirstAudioMs] = useState<number | null>(null);
  const askedAt = useRef<number | null>(null);
  const speaker = useRef<NeuralSpeaker | null>(null);
  const [readingUntil] = useState(() => Date.now());
  const started = useRef(false);
  const ending = useRef(false);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    startSession(caseId).then(setSession, (e: Error) => setError(e.message));
  }, [caseId]);

  const begin = useCallback(async () => {
    if (!session || session.phase !== "reading") return;
    askedAt.current = performance.now();
    try { setSession(await beginInterview(session.session_id)); setError(null); }
    catch (e) { setError((e as Error).message); }
  }, [session]);

  const finish = useCallback(async () => {
    if (!session || ending.current) return;
    ending.current = true;
    try { setDebrief(await endSession(session.session_id)); }
    catch (e) { ending.current = false; setError((e as Error).message); }
  }, [session]);

  const readingLeft = useCountdown(
    session?.phase === "reading" ? readingUntil + session.station.reading_seconds * 1000 : null,
    () => void begin(),
  );
  const deadline = session?.interview_deadline ? Date.parse(session.interview_deadline) : null;
  const matched = session ? pickVoice(voices, session.station.voice)?.name : undefined;
  const voiceName = voices.some((v) => v.name === voiceOverride) ? voiceOverride : matched;
  // The examiner's announcements use a different voice from the character's.
  const examiner = voices.find((v) => v.name !== voiceName)?.name ?? voiceName;
  const neuralOn = neural && !neuralFailed;
  // The case's own voice when it names an installed one, else one by presented sex and age.
  const kokoroMatched = !session ? undefined
    : session.station.voice?.speaker && KOKORO_NAMES.includes(session.station.voice.speaker) ? session.station.voice.speaker
    : characterVoice(presentedSex(session.station.id, session.station.voice?.sex), session.station.voice?.age);
  const kokoro = KOKORO_NAMES.includes(kokoroOverride) ? kokoroOverride : kokoroMatched;
  const sessionId = session?.session_id;

  // The character's neural voice: one speaker per session and voice.
  useEffect(() => {
    if (!sessionId || !neuralOn || !kokoro) return;
    const out = new WebAudioOut();
    const current = new NeuralSpeaker((text, signal) => synthesize(sessionId, text, kokoro, signal), out, {
      onFirstAudio: () => {
        if (askedAt.current === null) return;
        setFirstAudioMs(Math.round(performance.now() - askedAt.current));
        askedAt.current = null;
      },
      onFailure: () => { setNeuralFailed(true); setError("The character's voice is unavailable; replies use an on-device voice."); },
    });
    speaker.current = current;
    return () => { current.stop(); out.close(); if (speaker.current === current) speaker.current = null; };
  }, [sessionId, neuralOn, kokoro]);

  /** Read a character line aloud; `queue` adds it after what is already being said. */
  const readAloud = useCallback((text: string, queue = false) => {
    if (speaker.current) speaker.current.say(text);
    else speak(text, voiceName, { queue });
  }, [voiceName]);
  const hush = useCallback(() => { stopSpeaking(); speaker.current?.stop(); }, []);


  // A reply already in flight completes first; the server allows a short grace period.
  const interviewLeft = useCountdown(session?.phase === "interview" ? deadline : null, () => {
    if (spokenCues) speak("Time is up.", examiner);
    void finish();
  });

  // Exam timing cue: the one-minute warning, shown and optionally announced.
  const oneMinute = interviewLeft !== null && interviewLeft <= 60;
  const announced = useRef(false);
  useEffect(() => {
    if (!oneMinute || announced.current) return;
    announced.current = true;
    if (spokenCues) speak("You have one minute remaining.", examiner, { queue: true });
  }, [oneMinute, spokenCues, examiner]);

  // Read new character lines aloud when the candidate opts in.
  const spoken = useRef(0);
  const lines = session?.transcript.length ?? 0;
  useEffect(() => {
    const last = session?.transcript[lines - 1];
    if (lines > spoken.current && last?.speaker === "character" && speakReplies) readAloud(last.text);
    spoken.current = lines;
  }, [lines, session, speakReplies, readAloud]);
  useEffect(() => () => hush(), [hush]);

  // The current affect stage's hesitations, synthesised ahead (after the character's own
  // lines, so those are never delayed) so one can play at once while it thinks. Not logged:
  // they are authored fillers that carry no content.
  const fillers = useRef(new Map<string, SpeechView>());
  // Hesitations so far, and whether the last slow turn had one (never two in a row).
  const hesitated = useRef({ played: 0, lastSlow: false });
  const hesitations = session?.presentation.hesitations ?? [];
  const hesitationKey = hesitations.join("\n");
  useEffect(() => {
    if (!sessionId || !neuralOn || !speakReplies || !kokoro || pending || !hesitationKey) return;
    const controller = new AbortController();
    void (async () => {
      for (const text of hesitationKey.split("\n")) {
        const key = `${kokoro}|${text}`;
        if (fillers.current.has(key)) continue;
        try { fillers.current.set(key, await synthesize(sessionId, text, kokoro, controller.signal)); }
        catch { return; }
      }
    })();
    return () => controller.abort();
  }, [sessionId, neuralOn, speakReplies, kokoro, pending, hesitationKey]);

  async function submit(event?: FormEvent, spokenText?: string, spokenId?: string) {
    event?.preventDefault();
    const text = (spokenText ?? draft).trim();
    const id = spokenId ?? transcriptionId;
    if (!session || !text || pending) return;
    setPending(text); setDraft(""); setTranscriptionId(null); setError(null);
    hush();
    setFirstAudioMs(null);
    silenced.current = false;
    askedAt.current = performance.now();
    // On a slow turn the character may think aloud ("Hmmm.") midway through the wait. The
    // API says at once whether the turn will wait for the language model.
    let replied = false;
    let hesitate: ReturnType<typeof setTimeout> | undefined;
    const sentAt = performance.now();
    const pace = (slow: boolean) => {
      if (!slow) return;
      const sound = speakReplies ? hesitationFor(session.presentation.hesitations, slow, hesitated.current.lastSlow, hesitated.current.played) : null;
      hesitated.current.lastSlow = false;
      const prepared = sound ? fillers.current.get(`${kokoro}|${sound}`) : undefined;
      if (!prepared) return;
      hesitate = setTimeout(() => {
        if (replied || silenced.current || !speaker.current) return;
        speaker.current.play(prepared, sound!, HESITATION_VOLUME);
        hesitated.current = { played: hesitated.current.played + 1, lastSlow: true };
      }, Math.max(0, HESITATE_AFTER_MS - (performance.now() - sentAt)));
    };
    try {
      // Sentences arrive as the character speaks; read-aloud queues each one as it lands.
      const next = await sendTurnStream(session.session_id, text, id, (sentence, index) => {
        replied = true;
        setReply((previous) => [...previous, sentence]);
        if (speakReplies && !silenced.current) readAloud(sentence, index > 0);
      }, undefined, pace);
      // Already spoken sentence by sentence, so the read-aloud effect skips the final line.
      if (speakReplies) spoken.current = next.transcript.length;
      setSession(next);
    } catch (e) {
      hush();
      setDraft(text);
      // A 409 normally means the station has ended; a stale transcription is just reported.
      if (e instanceof ApiError && e.status === 409 && !/transcription/i.test(e.message)) void finish();
      else { setTranscriptionId(e instanceof ApiError && e.status === 409 ? null : id); setError((e as Error).message); }
    } finally { clearTimeout(hesitate); setPending(undefined); setReply([]); }
  }

  /** Hands-free: the trainee is talking. Over the character, that interrupts it. */
  function traineeSpeaking() {
    if (!session) return;
    if (characterSpeaking) {
      const heardMs = performance.now() - speakingSince.current;
      hush();
      void recordInterruption(session.session_id, "speaking", heardMs);
    } else if ((pending || speaker.current?.busy) && !silenced.current) {
      // The reply is still being prepared, or its voice is about to start: it is not read.
      silenced.current = true;
      hush();
      void recordInterruption(session.session_id, "thinking", 0);
    } else speaker.current?.duck(false); // the voice ended while ducked: restore it
  }

  /** Hands-free: what the trainee said is sent at once (or as soon as the reply lands). */
  function heardHandsFree(result: TranscriptionView, overlapped: boolean) {
    if (!session || !result.text) return;
    // The character's own voice picked up by the microphone, not the trainee.
    const lastCharacter = [...session.transcript].reverse().find((l) => l.speaker === "character")?.text;
    if (overlapped && isEcho(result.text, lastCharacter)) return;
    setError(null);
    if (pending) {
      const q = queued.current;
      // Two utterances during one reply are sent together (as typed: no single transcription).
      queued.current = q ? { text: `${q.text} ${result.text}`, id: null } : { text: result.text, id: result.transcription_id };
    }
    else void submit(undefined, result.text, result.transcription_id);
  }
  const submitRef = useRef(submit);
  useEffect(() => { submitRef.current = submit; });
  useEffect(() => {
    const next = queued.current;
    if (pending || !next) return;
    queued.current = null;
    void submitRef.current(undefined, next.text, next.id ?? undefined);
  }, [pending]);

  function heard(result: TranscriptionView) {
    if (!result.text) { setError("No speech was recognised. Please try again."); return; }
    setError(null);
    if (autoSend) void submit(undefined, result.text, result.transcription_id);
    else { setDraft(result.text); setTranscriptionId(result.transcription_id); }
  }

  function onKey(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void submit(); }
  }

  if (debrief) return <DebriefView debrief={debrief} onExit={onExit} />;
  if (!session) return <>
    {error ? <p className="error" role="alert">{error}</p> : <p className="empty">Preparing station…</p>}
    <button className="refresh" type="button" onClick={onExit}>Back to stations</button>
  </>;

  const station = session.station;
  return <section className="station-runner" aria-labelledby="runner-heading">
    <div className="runner-heading">
      <div>
        <p className="station-descriptors"><span className={`descriptor-skill skill-${station.skill}`}>{label(station.skill)}</span>{" "}
          <span className="descriptor-specialty">{label(station.specialty)}</span>{" "}
          <span className="descriptor-validation">Not clinically validated</span></p>
        <h1 id="runner-heading" aria-label={station.title}><StationTitle title={station.title} /></h1>
      </div>
      <div className={oneMinute ? "countdown ending" : "countdown"} role="timer" aria-label={session.phase === "reading" ? "Reading time remaining" : "Station time remaining"}>
        <span>{session.phase === "reading" ? "Reading" : "Station"}</span>
        <strong>{clock((session.phase === "reading" ? readingLeft : interviewLeft) ?? 0)}</strong>
      </div>
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    {oneMinute && session.phase === "interview" && <p className="cue" role="status">One minute remaining.</p>}
    {session.phase === "reading" ? <>
      <article className="instructions"><h2>Candidate instructions</h2><p>{station.candidate_instructions}</p></article>
      <button className="start" type="button" onClick={() => void begin()}>Begin interview now</button>
    </> : <>
      <details className="instructions"><summary>Candidate instructions</summary><p>{station.candidate_instructions}</p></details>
      <div className={showAvatar ? "stage with-avatar" : "stage"}>
        {showAvatar && <AvatarView avatarId={station.avatar ?? avatarFor(station.id, station.voice?.sex)}
          mood={session.presentation.expression}
          state={avatarState(pending, micPhase, draft)} label={`${session.character_name}, the simulated ${station.role}`} />}
        <Transcript session={session} pending={pending} reply={reply} />
      </div>
      <form className="composer" onSubmit={(e) => void submit(e)}>
        <label htmlFor="utterance" className="sr-only">What you say to {session.character_name}</label>
        <textarea id="utterance" rows={2} maxLength={600} value={draft} disabled={!!pending}
          placeholder={speech ? "Speak or type… (Enter to send; you can edit what was heard)" : `Speak to ${session.character_name}… (Enter to send)`}
          onChange={(e) => { setDraft(e.target.value); if (!e.target.value.trim()) setTranscriptionId(null); }}
          onKeyDown={onKey} />
        <div className="composer-actions">
          <div className="composer-send">
            {speech && handsFree && <HandsFree sessionId={session.session_id} characterName={session.character_name}
              characterSpeaking={characterSpeaking} listen={listen} onTraineeSpeaking={traineeSpeaking}
              onMaybeSpeaking={(maybe) => speaker.current?.duck(maybe && (characterSpeaking || !!speaker.current?.busy))}
              onPhase={setMicPhase} onTranscribed={heardHandsFree} onError={setError} />}
            {speech && !handsFree && <VoiceInput sessionId={session.session_id} characterName={session.character_name}
              disabled={!!pending} record={record} onStart={hush} onPhase={setMicPhase} onTranscribed={heard} onError={setError} />}
            <button className="start" type="submit" disabled={!!pending || !draft.trim()}>{pending ? "Waiting…" : "Send"}</button>
          </div>
          <button className="refresh" type="button" onClick={() => void finish()} disabled={!!pending}>End station</button>
        </div>
        <div className="composer-options">
          <label><input type="checkbox" checked={showAvatar}
            onChange={(e) => { setShowAvatar(e.target.checked); store("casc.showAvatar", e.target.checked); }} />
            Show the character (3D, experimental)</label>
          {speech && <label><input type="checkbox" checked={handsFree}
            onChange={(e) => { setHandsFree(e.target.checked); store("casc.handsFree", e.target.checked); setMicPhase("idle"); }} />
            Hands-free conversation (headphones recommended)</label>}
          {speech && !handsFree && <label><input type="checkbox" checked={autoSend}
            onChange={(e) => { setAutoSend(e.target.checked); store("casc.autoSend", e.target.checked); }} />
            Send speech without reviewing</label>}
          <label title={voiceAvailable || neuralOn ? undefined : "No on-device English voice is installed"}>
            <input type="checkbox" checked={speakReplies} disabled={!voiceAvailable && !neuralOn}
              onChange={(e) => { setSpeakReplies(e.target.checked); store("casc.speakReplies", e.target.checked); if (!e.target.checked) hush(); }} />
            Read replies aloud ({neuralOn ? "character voice" : "on-device voice"})</label>
          <label title={voiceAvailable ? undefined : "No on-device English voice is installed"}>
            <input type="checkbox" checked={spokenCues} disabled={!voiceAvailable}
              onChange={(e) => { setSpokenCues(e.target.checked); store("casc.spokenCues", e.target.checked); }} />
            Announce time cues</label>
          {speakReplies && neuralOn && <label>Voice
            <select value={KOKORO_NAMES.includes(kokoroOverride) ? kokoroOverride : ""}
              onChange={(e) => { setKokoroOverride(e.target.value); store(`casc.kokoro.${caseId}`, e.target.value); }}>
              <option value="">Automatic{kokoroMatched ? ` (${kokoroMatched})` : ""}</option>
              {KOKORO_NAMES.map((name) => <option key={name} value={name}>{name}</option>)}
            </select></label>}
          {speakReplies && neuralOn && firstAudioMs !== null &&
            <span className="muted" role="status">Reply audible after {(firstAudioMs / 1000).toFixed(1)} s</span>}
          {speakReplies && !neuralOn && voiceAvailable && <label>Voice
            <select value={voices.some((v) => v.name === voiceOverride) ? voiceOverride : ""}
              onChange={(e) => { setVoiceOverride(e.target.value); store(`casc.voice.${caseId}`, e.target.value); speak("Hello.", e.target.value || matched); }}>
              <option value="">Automatic{matched ? ` (${matched})` : ""}</option>
              {voices.map((v) => <option key={v.name} value={v.name}>{v.name} · {v.lang}</option>)}
            </select></label>}
        </div>
      </form>
    </>}
  </section>;
}
