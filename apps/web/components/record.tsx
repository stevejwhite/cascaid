"use client";

import { useEffect, useRef, useState } from "react";
import { readApi, saveRecording, type RecordingPrompts } from "../lib/api";
import { startRecording, type Recording, type StartRecording } from "../lib/recorder";

const SPEAKER = /^[a-z0-9][a-z0-9-]{1,30}$/;

/** Phase 4 evaluation tool: consenting speakers read prompts for the ASR evaluation. */
export function RecordPrompts({ record = startRecording }: { record?: StartRecording }) {
  const [data, setData] = useState<RecordingPrompts | null>(null);
  const [speaker, setSpeaker] = useState("");
  const [consent, setConsent] = useState(false);
  const [index, setIndex] = useState(0);
  const [phase, setPhase] = useState<"idle" | "recording" | "saving">("idle");
  const [saved, setSaved] = useState<Record<number, number>>({});
  const [error, setError] = useState<string | null>(null);
  const active = useRef<Recording | null>(null);

  useEffect(() => {
    readApi<RecordingPrompts>("/api/recordings/prompts").then(setData, () => setError("The local API is unavailable."));
    return () => active.current?.cancel();
  }, []);

  if (!data) return <main className="content">{error ? <p className="error" role="alert">{error}</p> : <p className="empty">Loading…</p>}</main>;
  if (!data.enabled) return <main className="content"><h1>Evaluation recordings</h1>
    <p className="notice">Recording is turned off. To collect evaluation recordings, set <code>RECORDINGS_ENABLED=true</code> in
      <code> .env</code> and restart <code>npm run dev</code>. Interview audio is never stored either way.</p></main>;

  const prompt = data.prompts[index];
  const ready = consent && SPEAKER.test(speaker);

  async function toggle() {
    setError(null);
    if (phase === "recording" && active.current) {
      const recording = active.current;
      active.current = null;
      setPhase("saving");
      try {
        const result = await saveRecording(speaker, prompt.item, await recording.stop());
        setSaved((s) => ({ ...s, [prompt.item]: result.duration_ms }));
        if (index < data!.prompts.length - 1) setIndex(index + 1);
      } catch (e) { setError((e as Error).message); }
      finally { setPhase("idle"); }
      return;
    }
    try { active.current = await record(); setPhase("recording"); }
    catch { setError("The microphone could not be used. Check the browser's microphone permission."); }
  }

  const done = Object.keys(saved).length;
  return <main className="content record">
    <p className="eyebrow">Phase 4 evaluation · audio saved locally</p>
    <h1>Evaluation recordings</h1>
    <p className="intro">Read each line aloud as you would say it to a patient or relative. Recordings go to
      <code> data/recordings/{speaker || "<pseudonym>"}</code> and are used only to measure speech recognition.</p>
    <label className="consent"><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /> {data.consent}</label>
    <label className="speaker">Pseudonym (lower-case letters, numbers, hyphens)
      <input value={speaker} onChange={(e) => setSpeaker(e.target.value.toLowerCase())} placeholder="e.g. speaker-01" disabled={phase !== "idle"} />
    </label>
    {error && <p className="error" role="alert">{error}</p>}
    <article className="prompt" aria-live="polite">
      <span>Prompt {index + 1} of {data.prompts.length} · {done} recorded this session{saved[prompt.item] ? " · this one saved" : ""}</span>
      <p>{prompt.text}</p>
    </article>
    <div className="composer-send">
      <button type="button" className={`mic ${phase}`} disabled={!ready || phase === "saving"} aria-pressed={phase === "recording"}
        onClick={() => void toggle()}><span aria-hidden="true" className="mic-dot" />
        {phase === "recording" ? "Stop and save" : phase === "saving" ? "Saving…" : saved[prompt.item] ? "Record again" : "Record"}</button>
      <button type="button" className="refresh" disabled={phase !== "idle" || index === 0} onClick={() => setIndex(index - 1)}>Previous</button>
      <button type="button" className="refresh" disabled={phase !== "idle" || index === data.prompts.length - 1} onClick={() => setIndex(index + 1)}>Skip</button>
    </div>
    <p className="muted">When finished: <code>npm run eval:asr -- --manifest data/recordings/{speaker || "<pseudonym>"}/manifest.yaml</code></p>
  </main>;
}
