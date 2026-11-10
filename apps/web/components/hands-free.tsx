"use client";

import { useEffect, useRef, useState } from "react";
import { encodeWav } from "../lib/audio";
import { transcribe, type TranscriptionView } from "../lib/api";
import type { Listener, StartListening } from "../lib/hands-free";
import type { VoicePhase } from "./voice";

interface Props {
  sessionId: string;
  characterName: string;
  /** The character's voice is playing (detection is stricter, and speaking interrupts it). */
  characterSpeaking: boolean;
  listen: StartListening;
  /** Possible speech (true) or a false start (false): the character's voice ducks meanwhile. */
  onMaybeSpeaking: (maybe: boolean) => void;
  /** Confirmed speech from the trainee (the station decides whether it interrupts). */
  onTraineeSpeaking: () => void;
  onPhase: (phase: VoicePhase) => void;
  /** A transcript, and whether its speech began while the character was speaking. */
  onTranscribed: (result: TranscriptionView, overlapped: boolean) => void;
  onError: (message: string) => void;
}

// Performance marks (hands-free:*) let latency be measured in the browser; nothing is sent.
const mark = (name: string) => performance.mark?.(`hands-free:${name}`);

/** Listens continuously while mounted: speech is transcribed and sent without clicking. */
export function HandsFree({ sessionId, characterName, characterSpeaking, listen, onMaybeSpeaking, onTraineeSpeaking, onPhase, onTranscribed, onError }: Props) {
  const [phase, setPhase] = useState<VoicePhase | "loading">("loading");
  const listener = useRef<Listener | null>(null);
  const speaking = useRef(characterSpeaking);
  const overlapped = useRef(false);
  // Latest callbacks, so the listener (created once) never calls stale ones.
  const handlers = useRef({ onMaybeSpeaking, onTraineeSpeaking, onPhase, onTranscribed, onError });
  useEffect(() => { handlers.current = { onMaybeSpeaking, onTraineeSpeaking, onPhase, onTranscribed, onError }; });
  useEffect(() => { onPhase(phase === "loading" ? "idle" : phase); }, [phase, onPhase]);

  useEffect(() => {
    speaking.current = characterSpeaking;
    listener.current?.setGuarded(characterSpeaking);
  }, [characterSpeaking]);

  useEffect(() => {
    let cancelled = false;
    let created: Listener | null = null;
    void listen({
      onSpeechStart: () => {
        mark("speech-start");
        overlapped.current = speaking.current;
        handlers.current.onMaybeSpeaking(true);
        setPhase("recording");
      },
      onSpeechConfirmed: () => { mark("speech-confirmed"); handlers.current.onTraineeSpeaking(); },
      onMisfire: () => { handlers.current.onMaybeSpeaking(false); setPhase("idle"); },
      onSpeechEnd: (audio) => {
        mark("speech-end");
        setPhase("transcribing");
        const wav = new Blob([encodeWav(audio)], { type: "audio/wav" });
        transcribe(sessionId, wav)
          .then((result) => { mark("transcribed"); handlers.current.onTranscribed(result, overlapped.current); })
          .catch((error: Error) => handlers.current.onError(error.message))
          .finally(() => setPhase("idle"));
      },
    }).then(async (ready) => {
      created = ready;
      if (cancelled) { await ready.destroy(); return; }
      listener.current = ready;
      ready.setGuarded(speaking.current);
      await ready.start();
      setPhase("idle");
    }, () => {
      if (!cancelled) handlers.current.onError("Hands-free listening could not start. Check the microphone permission, or turn hands-free off to click to talk.");
    });
    return () => { cancelled = true; listener.current = null; void created?.destroy(); };
  }, [sessionId, listen]);

  const label = phase === "loading" ? "Starting to listen…"
    : phase === "recording" ? "Hearing you…"
      : phase === "transcribing" ? "Transcribing…" : `Listening — just speak to ${characterName}`;
  return <p className={`mic hands-free ${phase}`} role="status" aria-live="polite">
    <span aria-hidden="true" className="mic-dot" />{label}
  </p>;
}
