"use client";

import { useEffect, useRef, useState } from "react";
import { transcribe, type TranscriptionView } from "../lib/api";
import { type Recording, type StartRecording } from "../lib/recorder";

export const MAX_RECORDING_SECONDS = 60;

export function stored(key: string, fallback: boolean): boolean {
  try { const value = window.localStorage.getItem(key); return value === null ? fallback : value === "true"; }
  catch { return fallback; }
}

export function store(key: string, value: boolean | string) {
  try { window.localStorage.setItem(key, String(value)); } catch { /* preference only */ }
}

export function storedText(key: string): string {
  try { return window.localStorage.getItem(key) ?? ""; } catch { return ""; }
}

interface Props {
  sessionId: string;
  characterName: string;
  disabled: boolean;
  record: StartRecording;
  onStart: () => void;
  /** Reports the recording phase (the avatar listens while the trainee speaks). */
  onPhase?: (phase: VoicePhase) => void;
  onTranscribed: (result: TranscriptionView) => void;
  onError: (message: string) => void;
}

/** Push-to-talk: click to start, click again to stop and transcribe on this machine. */
export type VoicePhase = "idle" | "starting" | "recording" | "transcribing";

export function VoiceInput({ sessionId, characterName, disabled, record, onStart, onPhase, onTranscribed, onError }: Props) {
  const [phase, setPhase] = useState<VoicePhase>("idle");
  useEffect(() => { onPhase?.(phase); }, [phase, onPhase]);
  const [seconds, setSeconds] = useState(0);
  const recording = useRef<Recording | null>(null);

  useEffect(() => () => recording.current?.cancel(), []);

  async function start() {
    onStart();
    setPhase("starting");
    try {
      recording.current = await record();
      setSeconds(0);
      setPhase("recording");
    } catch {
      setPhase("idle");
      onError("The microphone could not be used. Check the browser's microphone permission.");
    }
  }

  async function stop() {
    const active = recording.current;
    if (!active) return;
    recording.current = null;
    setPhase("transcribing");
    try {
      onTranscribed(await transcribe(sessionId, await active.stop()));
    } catch (error) {
      onError((error as Error).message);
    } finally { setPhase("idle"); }
  }

  const stopRef = useRef(stop);
  useEffect(() => { stopRef.current = stop; });
  useEffect(() => {
    if (phase !== "recording") return;
    const started = Date.now();
    const timer = setInterval(() => {
      const elapsed = (Date.now() - started) / 1000;
      setSeconds(Math.floor(elapsed));
      if (elapsed >= MAX_RECORDING_SECONDS) void stopRef.current();
    }, 250);
    return () => clearInterval(timer);
  }, [phase]);

  const label = phase === "recording" ? `Stop and transcribe (${seconds}s)`
    : phase === "transcribing" ? "Transcribing…"
      : phase === "starting" ? "Opening microphone…" : `Speak to ${characterName}`;
  return <button type="button" className={`mic ${phase}`} aria-pressed={phase === "recording"}
    disabled={(disabled && phase !== "recording") || phase === "transcribing" || phase === "starting"}
    onClick={() => void (phase === "recording" ? stop() : start())}>
    <span aria-hidden="true" className="mic-dot" />{label}
  </button>;
}
