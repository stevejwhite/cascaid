import type { Cue } from "./lipsync";

/**
 * Events from read-aloud speech, for the avatar's mouth. The speech code (lib/recorder.ts
 * for browser voices, lib/neural-voice.ts for the character's voice) emits them; the avatar
 * listens. Nothing is recorded or stored.
 */

export type SpeechEvent =
  | { type: "start"; text: string }
  // Browser voices report word boundaries only; the mouth shapes are estimated from text.
  | { type: "word"; text: string; charIndex: number; charLength: number }
  // The neural voice gives exact viseme timings, in seconds from the moment sound starts.
  | { type: "cues"; cues: Cue[] }
  | { type: "end" };

type Listener = (event: SpeechEvent) => void;
const listeners = new Set<Listener>();

export function onSpeech(listener: Listener): () => void {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}

export function emitSpeech(event: SpeechEvent) {
  for (const listener of listeners) listener(event);
}

/** The word starting at charIndex, when the voice does not report its length. */
export function wordAt(text: string, charIndex: number, charLength = 0): string {
  if (charLength > 0) return text.slice(charIndex, charIndex + charLength);
  const match = text.slice(charIndex).match(/^[\w'’-]+/);
  return match ? match[0] : "";
}
