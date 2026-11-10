import { afterEach, expect, test, vi } from "vitest";
import type { SpeechView } from "../lib/api";
import { onSpeech, type SpeechEvent } from "../lib/avatar/speech";
import { characterVoice, decodeBase64, hesitationFor, KOKORO_NAMES, leadingSilence, NeuralSpeaker, speechCues, type AudioOut } from "../lib/neural-voice";

const view = (text: string, first = 460): SpeechView => ({
  audio_wav_base64: btoa(text), words: text.split(" "), word_times_ms: [first], word_durations_ms: [200],
  visemes: ["PP", "aa"], viseme_times_ms: [first, first + 100], viseme_durations_ms: [100, 150],
  voice: "af_bella", model: "kokoro", synthesis_ms: 300,
});

/** Records what is played; each sound ends when the test says so. */
function fakeOut() {
  const played: { text: string; offset: number }[] = [];
  const endings: (() => void)[] = [];
  const out: AudioOut = {
    play: (wav, offset, onStart) => new Promise<void>((resolve) => {
      played.push({ text: new TextDecoder().decode(wav), offset }); onStart(); endings.push(resolve);
    }),
    stop: vi.fn(() => endings.splice(0).forEach((end) => end())),
  };
  const finishOne = async () => { endings.shift()?.(); await flush(); };
  return { out, played, finishOne };
}

const flush = () => new Promise((resolve) => setTimeout(resolve, 0));
let unsubscribe = () => {};
afterEach(() => unsubscribe());
function events(): SpeechEvent[] {
  const seen: SpeechEvent[] = [];
  unsubscribe = onSpeech((e) => seen.push(e));
  return seen;
}

test("each character has a voice from the installed set, by presented sex and age", () => {
  expect(characterVoice("female")).toBe("af_bella");
  expect(characterVoice("male", "older")).toBe("am_fenrir");
  expect(characterVoice("female", "young")).toBe("af_heart");
  expect(KOKORO_NAMES).toHaveLength(6);
});

test("the leading silence is trimmed and viseme cues are shifted to match", () => {
  const speech = view("Hello there.", 460);
  expect(leadingSilence(speech)).toBeCloseTo(0.34);
  expect(leadingSilence(view("x", 50))).toBe(0);
  const cues = speechCues(speech, leadingSilence(speech));
  expect(cues[0]).toEqual({ viseme: "PP", start: expect.closeTo(0.12), end: expect.closeTo(0.22) });
  expect(cues[1].viseme).toBe("aa");
  expect(new TextDecoder().decode(decodeBase64(btoa("RIFF")))).toBe("RIFF");
});

test("sentences play in order even when a later one is synthesised first", async () => {
  const seen = events();
  const resolvers: Record<string, (v: SpeechView) => void> = {};
  const synth = vi.fn((text: string) => new Promise<SpeechView>((resolve) => { resolvers[text] = resolve; }));
  const { out, played, finishOne } = fakeOut();
  const first = vi.fn();
  const speaker = new NeuralSpeaker(synth, out, { onFirstAudio: first });
  speaker.say("One."); speaker.say("Two.");
  expect(synth).toHaveBeenCalledTimes(2); // both requested straight away
  resolvers["Two."](view("Two."));
  await flush();
  expect(played).toEqual([]);
  resolvers["One."](view("One."));
  await flush();
  expect(played.map((p) => p.text)).toEqual(["One."]);
  await finishOne();
  expect(played.map((p) => p.text)).toEqual(["One.", "Two."]);
  await finishOne();
  expect(first).toHaveBeenCalledTimes(1);
  expect(seen.map((e) => e.type)).toEqual(["start", "cues", "cues", "end"]);
  expect(speaker.busy).toBe(false);
});

test("stopping cancels pending synthesis and silences the character at once", async () => {
  const seen = events();
  const signals: AbortSignal[] = [];
  const synth = vi.fn((text: string, signal: AbortSignal) => {
    signals.push(signal);
    return text === "One." ? Promise.resolve(view(text)) : new Promise<SpeechView>(() => {});
  });
  const { out, played } = fakeOut();
  const failure = vi.fn();
  const speaker = new NeuralSpeaker(synth, out, { onFailure: failure });
  speaker.say("One."); speaker.say("Two.");
  await flush();
  speaker.stop();
  expect(signals.every((s) => s.aborted)).toBe(true);
  expect(out.stop).toHaveBeenCalled();
  await flush();
  expect(played.map((p) => p.text)).toEqual(["One."]);
  expect(seen.at(-1)).toEqual({ type: "end" });
  expect(failure).not.toHaveBeenCalled();
  speaker.say("Three.");
  expect(signals.at(-1)!.aborted).toBe(false);
});

test("a sentence that cannot be synthesised is reported and the rest still play", async () => {
  const synth = vi.fn(async (text: string) => { if (text === "One.") throw new Error("503"); return view(text); });
  const { out, played, finishOne } = fakeOut();
  const failure = vi.fn();
  const speaker = new NeuralSpeaker(synth, out, { onFailure: failure });
  speaker.say("One."); speaker.say("Two.");
  await flush();
  expect(failure).toHaveBeenCalledWith("One.", expect.any(Error));
  expect(played.map((p) => p.text)).toEqual(["Two."]);
  await finishOne();
});

test("hesitations come only on slow turns, never twice running, rotating through the sounds", () => {
  const sounds = ["Hmmm.", "Mm."];
  expect(hesitationFor(sounds, false, false, 0)).toBeNull(); // a fast turn
  expect(hesitationFor(sounds, true, false, 0)).toBe("Hmmm.");
  expect(hesitationFor(sounds, true, true, 1)).toBeNull(); // the last slow turn had one
  expect(hesitationFor(sounds, true, false, 1)).toBe("Mm.");
  expect(hesitationFor([], true, false, 0)).toBeNull();
});

test("prepared audio queues in order with synthesised sentences", async () => {
  const { out, played, finishOne } = fakeOut();
  const first = vi.fn();
  const speaker = new NeuralSpeaker(async (text) => view(text), out, { onFirstAudio: first });
  speaker.play(view("Mm."));
  speaker.say("Right.");
  await flush();
  expect(played.map((p) => p.text)).toEqual(["Mm."]);
  expect(first).not.toHaveBeenCalled(); // a hesitation is not the reply
  await finishOne();
  expect(played.map((p) => p.text)).toEqual(["Mm.", "Right."]);
  expect(first).toHaveBeenCalledTimes(1);
  await finishOne();
});

test("synthesis cancelled by stopping is not reported as a failure", async () => {
  const synth = vi.fn((_: string, signal: AbortSignal) => new Promise<SpeechView>((_, reject) =>
    signal.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")))));
  const { out } = fakeOut();
  const failure = vi.fn();
  const speaker = new NeuralSpeaker(synth, out, { onFailure: failure });
  speaker.say("One.");
  speaker.stop();
  await flush();
  expect(failure).not.toHaveBeenCalled();
});
