"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { MOODS, type AvatarState, type Mood } from "../lib/avatar/behaviour";
import { emitSpeech } from "../lib/avatar/speech";
import { estimateDuration } from "../lib/avatar/lipsync";
import { speak, stopSpeaking } from "../lib/recorder";

const AvatarView = dynamic(() => import("./avatar-view"), { ssr: false });

const STATES: AvatarState[] = ["idle", "listening", "thinking", "speaking"];
const EXPRESSIONS = Object.keys(MOODS) as Mood[];

/** Sends the word events a voice would, at speaking pace, without any audio. */
function mouthTest(text: string) {
  emitSpeech({ type: "start", text });
  let delay = 0;
  for (const match of text.matchAll(/[\w'’-]+/g)) {
    const word = match[0], at = match.index ?? 0;
    setTimeout(() => emitSpeech({ type: "word", text, charIndex: at, charLength: word.length }), delay * 1000);
    delay += estimateDuration(word) + 0.06;
  }
  setTimeout(() => emitSpeech({ type: "end" }), delay * 1000 + 200);
}

/** Development page for tuning the avatar's states, moods and lip-sync (/avatar-lab). */
export function AvatarLab() {
  const [avatarId, setAvatarId] = useState("female-adult-01");
  const [state, setState] = useState<AvatarState>("idle");
  const [mood, setMood] = useState<Mood>("neutral");
  // Every installed character, from the manifest npm run avatars:install writes.
  const [installed, setInstalled] = useState<string[]>(["female-adult-01", "male-adult-08"]);
  useEffect(() => {
    fetch("/avatars/manifest.json").then((r) => r.json())
      .then((m: { avatars: { id: string }[] }) => setInstalled(m.avatars.map((a) => a.id)), () => {});
  }, []);
  const [text, setText] = useState("I get through about a litre bottle of vodka a day, sometimes more at the weekend.");
  return <section className="avatar-lab">
    <h1>Avatar lab</h1>
    <p className="muted">Development page: not part of a station. Characters from the Microsoft Rocketbox library (MIT).</p>
    <div className="avatar-lab-grid">
      <AvatarView avatarId={avatarId} state={state} mood={mood} label={`Character ${avatarId}`} />
      <div className="avatar-lab-controls">
        <label>Model <select value={avatarId} onChange={(e) => setAvatarId(e.target.value)}>
          {installed.map((id) => <option key={id} value={id}>{id}</option>)}
        </select></label>
        <fieldset><legend>State</legend>{STATES.map((s) =>
          <label key={s}><input type="radio" name="state" checked={state === s} onChange={() => setState(s)} /> {s}</label>)}</fieldset>
        <fieldset><legend>Expression</legend>{EXPRESSIONS.map((m) =>
          <label key={m}><input type="radio" name="mood" checked={mood === m} onChange={() => setMood(m)} /> {m}</label>)}</fieldset>
        <label>Say <textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} /></label>
        <div className="composer-send">
          <button className="start" type="button" onClick={() => speak(text)}>Speak</button>
          <button className="refresh" type="button" onClick={() => stopSpeaking()}>Stop</button>
          <button className="refresh" type="button" onClick={() => mouthTest(text)}>Mouth test (no audio)</button>
        </div>
      </div>
    </div>
  </section>;
}
