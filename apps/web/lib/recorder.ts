import { emitSpeech } from "./avatar/speech";
import { concat, encodeWav, resample } from "./audio";
import { usableVoices } from "./voices";

/** One microphone recording. Audio stays in memory and is sent only to the local API. */
export interface Recording {
  stop(): Promise<Blob>;
  cancel(): void;
}

export type StartRecording = () => Promise<Recording>;

// Copies each render quantum to the main thread; loaded from a Blob URL so no extra file is served.
const CAPTURE = `class Capture extends AudioWorkletProcessor {
  process(inputs) { const channel = inputs[0] && inputs[0][0]; if (channel) this.port.postMessage(channel.slice(0)); return true; }
}
registerProcessor("capture", Capture);`;

export const startRecording: StartRecording = async () => {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
  });
  const context = new AudioContext();
  const url = URL.createObjectURL(new Blob([CAPTURE], { type: "application/javascript" }));
  try {
    await context.audioWorklet.addModule(url);
  } finally {
    URL.revokeObjectURL(url);
  }
  const chunks: Float32Array[] = [];
  const source = context.createMediaStreamSource(stream);
  const capture = new AudioWorkletNode(context, "capture");
  // A silent sink keeps the graph running in browsers that skip unconnected nodes.
  const silent = context.createGain();
  silent.gain.value = 0;
  capture.port.onmessage = (event: MessageEvent<Float32Array>) => chunks.push(event.data);
  source.connect(capture).connect(silent).connect(context.destination);

  const release = () => {
    source.disconnect();
    capture.disconnect();
    stream.getTracks().forEach((track) => track.stop());
    void context.close();
  };
  return {
    async stop() {
      const rate = context.sampleRate;
      release();
      return new Blob([encodeWav(resample(concat(chunks), rate))], { type: "audio/wav" });
    },
    cancel: release,
  };
};

/** Speak text with an on-device voice; network voices are never used.
 *  `queue` adds to what is already being spoken (sentences of a streamed reply). */
export function speak(text: string, voiceName?: string, { queue = false } = {}): boolean {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return false;
  const voices = usableVoices(window.speechSynthesis.getVoices());
  const voice = voices.find((v) => v.name === voiceName) ?? voices[0];
  if (!voice) return false;
  if (!queue) window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.voice = voice as SpeechSynthesisVoice;
  utterance.lang = voice.lang;
  // The avatar's mouth follows these events (word boundaries only; no audio access).
  utterance.onstart = () => emitSpeech({ type: "start", text });
  utterance.onboundary = (e) => {
    if (!e.name || e.name === "word") emitSpeech({ type: "word", text, charIndex: e.charIndex, charLength: e.charLength ?? 0 });
  };
  utterance.onend = utterance.onerror = () => emitSpeech({ type: "end" });
  window.speechSynthesis.speak(utterance);
  return true;
}

export function stopSpeaking() {
  if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
  emitSpeech({ type: "end" });
}

/** Names of usable on-device voices, joined: a stable snapshot for useSyncExternalStore. */
export function voiceNames(): string {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return "";
  return usableVoices(window.speechSynthesis.getVoices()).map((v) => `${v.name}\t${v.lang}`).join("\n");
}

export function localVoiceAvailable(): boolean {
  return voiceNames() !== "";
}

/** Browsers load voices asynchronously; subscribe for useSyncExternalStore. */
export function onVoicesChanged(callback: () => void): () => void {
  if (typeof window === "undefined" || !("speechSynthesis" in window)) return () => {};
  window.speechSynthesis.addEventListener("voiceschanged", callback);
  return () => window.speechSynthesis.removeEventListener("voiceschanged", callback);
}
