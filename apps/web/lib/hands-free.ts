/**
 * Hands-free conversation: Silero VAD (v5, MIT) runs in the page on the microphone and finds
 * where the trainee's speech starts and ends, so nobody has to click. The model and its
 * runtime are served from this app (public/vad), never a CDN. Audio stays in memory and
 * goes only to the local API for transcription.
 */

/** Silence that ends the trainee's turn. Shorter cuts people off mid-thought. */
export const END_OF_SPEECH_MS = 600;
/** Speech this long counts as the trainee talking (and interrupts the character). */
export const CONFIRM_SPEECH_MS = 250;

// Detection thresholds: normal, and stricter while the character's own voice is playing so
// its echo through the speakers is less likely to count as the trainee.
const NORMAL = { positiveSpeechThreshold: 0.5, negativeSpeechThreshold: 0.35, minSpeechMs: CONFIRM_SPEECH_MS };
const GUARDED = { positiveSpeechThreshold: 0.85, negativeSpeechThreshold: 0.6, minSpeechMs: 400 };

export interface ListenerEvents {
  /** Possible speech: the character can look attentive. */
  onSpeechStart: () => void;
  /** Speech confirmed (CONFIRM_SPEECH_MS): the trainee is talking. */
  onSpeechConfirmed: () => void;
  /** End of speech, with the utterance as 16 kHz mono samples. */
  onSpeechEnd: (audio: Float32Array) => void;
  /** It was not speech after all (too short). */
  onMisfire: () => void;
}

export interface Listener {
  start(): Promise<void>;
  pause(): Promise<void>;
  destroy(): Promise<void>;
  /** Stricter detection while the character is speaking. */
  setGuarded(guarded: boolean): void;
}

export type StartListening = (events: ListenerEvents) => Promise<Listener>;

export const startListening: StartListening = async (events) => {
  const { MicVAD } = await import("@ricky0123/vad-web");
  const vad = await MicVAD.new({
    model: "v5",
    baseAssetPath: "/vad/",
    onnxWASMBasePath: "/vad/",
    startOnLoad: false,
    ...NORMAL,
    redemptionMs: END_OF_SPEECH_MS,
    preSpeechPadMs: 300,
    onSpeechStart: events.onSpeechStart,
    onSpeechRealStart: events.onSpeechConfirmed,
    onSpeechEnd: events.onSpeechEnd,
    onVADMisfire: events.onMisfire,
    ortConfig: (ort) => {
      ort.env.logLevel = "error";
      // One thread: the page is not cross-origin isolated, and the model is tiny.
      ort.env.wasm.numThreads = 1;
    },
  });
  return {
    start: () => vad.start(),
    pause: () => vad.pause(),
    // A listener destroyed before it started (React remounts in development) has no stream.
    destroy: () => Promise.resolve().then(() => vad.destroy()).catch(() => {}),
    setGuarded: (guarded) => vad.setOptions(guarded ? GUARDED : NORMAL),
  };
};

function words(text: string): string[] {
  return text.toLowerCase().match(/[a-z']+/g) ?? [];
}

/**
 * Whether a transcript is the character's own voice picked up by the microphone: most of
 * its words (at least three) appear in what the character just said.
 */
export function isEcho(transcript: string, characterLine: string | undefined): boolean {
  const heard = words(transcript);
  if (!characterLine || heard.length < 3) return false;
  const said = new Set(words(characterLine));
  return heard.filter((w) => said.has(w)).length / heard.length >= 0.8;
}
