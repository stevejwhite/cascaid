/**
 * The character's neural voice (Kokoro-82M on the local API): each released sentence is
 * synthesised, played in order through WebAudio, and its viseme timings drive the avatar's
 * mouth. Audio stays in memory; nothing is stored.
 */

import type { SpeechView } from "./api";
import type { Cue } from "./avatar/lipsync";
import { emitSpeech } from "./avatar/speech";

/** Installed American Kokoro voices (config/tts-runtime.json), by presented sex and age. */
export const KOKORO_VOICES = {
  female: { young: "af_heart", adult: "af_bella", older: "af_sarah" },
  male: { young: "am_puck", adult: "am_michael", older: "am_fenrir" },
} as const;

export const KOKORO_NAMES: readonly string[] = Object.values(KOKORO_VOICES).flatMap((v) => Object.values(v));

export function characterVoice(sex: "female" | "male", age: "young" | "adult" | "older" = "adult"): string {
  return KOKORO_VOICES[sex][age];
}

// Kokoro pads each sentence with about half a second of silence; start a little before the
// first word instead, which shortens the wait for the first sound.
const LEAD_IN_MS = 120;

export function leadingSilence(speech: Pick<SpeechView, "word_times_ms">): number {
  return Math.max(0, (speech.word_times_ms[0] ?? 0) - LEAD_IN_MS) / 1000;
}

/** Viseme cues in seconds from the moment playback starts at `offset` into the audio. */
export function speechCues(speech: Pick<SpeechView, "visemes" | "viseme_times_ms" | "viseme_durations_ms">,
  offset = 0): Cue[] {
  return speech.visemes.map((viseme, i) => ({
    viseme,
    start: speech.viseme_times_ms[i] / 1000 - offset,
    end: (speech.viseme_times_ms[i] + speech.viseme_durations_ms[i]) / 1000 - offset,
  }));
}

export function decodeBase64(data: string): ArrayBuffer {
  const bytes = Uint8Array.from(atob(data), (c) => c.charCodeAt(0));
  return bytes.buffer;
}

/** Where audio is played; WebAudio in the browser, a fake in tests. */
export interface AudioOut {
  /** Play from `offset` seconds in at `volume` (0–1); calls onStart as sound begins;
   *  resolves when it ends or is stopped. */
  play(wav: ArrayBuffer, offset: number, onStart: () => void, volume?: number): Promise<void>;
  stop(): void;
  /** Lower the volume at once (the trainee may be starting to speak), or restore it. */
  duck?(on: boolean): void;
}

/** Volume while ducked: the character audibly yields but can still be heard. */
export const DUCKED_GAIN = 0.2;

export class WebAudioOut implements AudioOut {
  private context: AudioContext | null = null;
  private gain: GainNode | null = null;
  private source: AudioBufferSourceNode | null = null;
  private finish: (() => void) | null = null;

  /** Create or resume the audio context; call from a user action (autoplay rules). */
  prime() {
    if (!this.context) {
      this.context = new AudioContext();
      this.gain = this.context.createGain();
      this.gain.connect(this.context.destination);
    }
    if (this.context.state === "suspended") void this.context.resume();
  }

  async play(wav: ArrayBuffer, offset: number, onStart: () => void, volume = 1) {
    this.prime();
    const context = this.context!;
    const buffer = await context.decodeAudioData(wav);
    await new Promise<void>((resolve) => {
      const source = context.createBufferSource();
      source.buffer = buffer;
      const level = context.createGain();
      level.gain.value = volume;
      source.connect(level).connect(this.gain ?? context.destination);
      this.source = source;
      this.finish = resolve;
      source.onended = () => {
        if (this.source === source) { this.source = null; this.finish = null; }
        resolve();
      };
      source.start(0, Math.min(offset, buffer.duration));
      onStart();
    });
  }

  stop() {
    const source = this.source;
    this.source = null;
    try { source?.stop(); } catch { /* already stopped */ }
    this.finish?.();
    this.finish = null;
    this.duck(false);
  }

  duck(on: boolean) {
    if (!this.context || !this.gain) return;
    // A 20 ms glide: immediate to the ear, without a click.
    this.gain.gain.setTargetAtTime(on ? DUCKED_GAIN : 1, this.context.currentTime, 0.02);
    if (on) performance.mark?.("voice:ducked");
  }

  close() { this.stop(); void this.context?.close(); this.context = null; }
}

export type Synthesise = (text: string, signal: AbortSignal) => Promise<SpeechView>;

export interface SpeakerEvents {
  /** The first sound of a run of sentences (to measure time to first audio). */
  onFirstAudio?: () => void;
  /** A sentence could not be synthesised (the caller may read it another way). */
  onFailure?: (text: string, error: unknown) => void;
}

/**
 * Sentences are synthesised as soon as they are queued (the API runs one at a time, never
 * while the language model generates) and played strictly in order.
 */
export class NeuralSpeaker {
  private queue: { text: string; speech: Promise<SpeechView | null>; prepared?: boolean; volume?: number }[] = [];
  private controller = new AbortController();
  private generation = 0;
  private playing = false;

  constructor(private synthesise: Synthesise, private out: AudioOut, private events: SpeakerEvents = {}) {}

  /** Queue audio that is already synthesised (an authored hesitation); it does not count
   *  as the reply's first audio. */
  play(speech: SpeechView, text = speech.words.join(" "), volume = 1) {
    this.queue.push({ text, speech: Promise.resolve(speech), prepared: true, volume });
    if (!this.playing) void this.drain(this.generation);
  }

  say(text: string) {
    // This request's own signal: stop() replaces the controller before the abort lands.
    const signal = this.controller.signal;
    const speech = this.synthesise(text, signal).catch((error: unknown) => {
      if (!signal.aborted) this.events.onFailure?.(text, error);
      return null;
    });
    this.queue.push({ text, speech });
    if (!this.playing) void this.drain(this.generation);
  }

  get busy() { return this.playing; }

  private async drain(generation: number) {
    this.playing = true;
    this.out.duck?.(false); // a new reply starts at full volume
    let first = true, measured = false;
    while (this.queue.length && generation === this.generation) {
      const { text, speech: pending, prepared, volume } = this.queue.shift()!;
      const speech = await pending;
      if (generation !== this.generation) return;
      if (!speech) continue;
      const offset = leadingSilence(speech);
      await this.out.play(decodeBase64(speech.audio_wav_base64), offset, () => {
        if (generation !== this.generation) return;
        if (first) { first = false; emitSpeech({ type: "start", text }); }
        if (!prepared && !measured) { measured = true; performance.mark?.("voice:first-audio"); this.events.onFirstAudio?.(); }
        emitSpeech({ type: "cues", cues: speechCues(speech, offset) });
      }, volume);
    }
    if (generation !== this.generation) return;
    this.playing = false;
    if (!first) emitSpeech({ type: "end" });
  }

  /** Lower or restore the volume of what is playing (see AudioOut.duck). */
  duck(on: boolean) { this.out.duck?.(on); }

  /** Stop at once: cancel pending synthesis, silence playback (the trainee is speaking). */
  stop() {
    this.generation++;
    this.controller.abort();
    this.controller = new AbortController();
    this.queue = [];
    const wasPlaying = this.playing;
    this.playing = false;
    this.out.stop();
    if (wasPlaying) { performance.mark?.("voice:stopped"); emitSpeech({ type: "end" }); }
  }
}

/** On a slow turn, the hesitation comes this long after sending: about midway through
 *  the wait (the reply is typically audible after 4–5 s). */
export const HESITATE_AFTER_MS = 1800;

/** Hesitations are a little quieter than speech: thinking aloud, not answering. */
export const HESITATION_VOLUME = 0.7;

/**
 * The hesitation for a turn, if any. Only on slow turns (the reply waits for the language
 * model); never on two slow turns in a row; rotating through the affect stage's sounds.
 * Deterministic: no randomness.
 */
export function hesitationFor(sounds: readonly string[], slow: boolean, lastSlowHesitated: boolean,
  played: number): string | null {
  if (!slow || lastSlowHesitated || !sounds.length) return null;
  return sounds[played % sounds.length];
}
