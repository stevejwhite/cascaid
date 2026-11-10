import { expect, test } from "vitest";
import { BEARING, Behaviour, MOODS, type Mood } from "../lib/avatar/behaviour";
import { cuesForWord, estimateDuration, weightsAt, wordVisemes } from "../lib/avatar/lipsync";
import { emitSpeech, onSpeech, wordAt } from "../lib/avatar/speech";

// A repeatable random source, so behaviour can be checked exactly.
function seeded(seed = 1) {
  return () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
}

test("words map to visemes that open on vowels and close on p, b and m", () => {
  expect(wordVisemes("mum")).toEqual(["PP", "U", "PP"]);
  expect(wordVisemes("vodka")).toEqual(["FF", "O", "DD", "kk", "aa"]);
  expect(wordVisemes("the")).toEqual(["TH", "E"]);
  expect(wordVisemes("...")).toEqual([]);
});

test("cues fill the word's duration and cross-fade into weights", () => {
  const cues = cuesForWord("ma", 1, 0.2);
  expect(cues).toEqual([{ viseme: "PP", start: 1, end: 1.1 }, { viseme: "aa", start: 1.1, end: 1.2 }]);
  expect(weightsAt(cues, 1.15).viseme_aa).toBeGreaterThan(0.8);
  expect(weightsAt(cues, 2)).toEqual({});
  expect(estimateDuration("a")).toBe(0.14);
  expect(estimateDuration("x".repeat(40))).toBe(0.75);
});

test("the character blinks every few seconds and briefly", () => {
  const b = new Behaviour(seeded());
  const closed: number[] = [];
  for (let t = 0; t < 20; t += 0.02) if (b.update(t).morphs.eyeBlinkLeft > 0.9) closed.push(t);
  const blinks = closed.filter((t, i) => i === 0 || t - closed[i - 1] > 0.5).length;
  expect(blinks).toBeGreaterThanOrEqual(3);
  expect(blinks).toBeLessThanOrEqual(10);
});

test("thinking looks away; listening mostly holds eye contact", () => {
  const thinking = new Behaviour(seeded(3));
  thinking.setState("thinking", 0);
  const away = thinking.update(0.1).eyes;
  expect(Math.abs(away.yaw)).toBeGreaterThan(0.15);
  const listening = new Behaviour(seeded(5));
  listening.setState("listening", 0);
  let contact = 0, frames = 0;
  for (let t = 0; t < 30; t += 0.1) { const e = listening.update(t).eyes; frames++; if (e.yaw === 0 && e.pitch === 0) contact++; }
  expect(contact / frames).toBeGreaterThan(0.6);
});

test("moods add a light baseline expression and mouth weights pass through", () => {
  const b = new Behaviour(seeded());
  b.update(0);
  b.setMood("sad");
  b.setMouth({ viseme_aa: 0.7 });
  const f = b.update(5);
  expect(f.morphs.browInnerUp).toBeGreaterThan(0.3);
  expect(f.morphs.viseme_aa).toBe(0.7);
});

test("an affect change shows over about a second rather than snapping", () => {
  const b = new Behaviour(seeded());
  b.update(0);
  b.setMood("tearful");
  const soon = b.update(0.1).morphs.browInnerUp ?? 0;
  const later = b.update(0.6).morphs.browInnerUp ?? 0;
  const settled = b.update(4).morphs.browInnerUp ?? 0;
  expect(soon).toBeGreaterThan(0);
  expect(soon).toBeLessThan(later);
  expect(later).toBeLessThan(settled);
  expect(settled).toBeCloseTo(MOODS.tearful.browInnerUp, 2);
  b.setMood("neutral");
  expect(b.update(10).morphs.browInnerUp ?? 0).toBeLessThan(0.01);
});

test("a flat, guarded character looks down and away more than a neutral one", () => {
  const run = (mood: Mood) => {
    const b = new Behaviour(seeded(9));
    b.setMood(mood);
    b.setState("listening", 0);
    let contact = 0, pitch = 0, frames = 0;
    for (let t = 0; t < 60; t += 0.1) {
      const f = b.update(t);
      if (t < 3) continue;
      frames++; pitch += f.head.pitch;
      if (f.eyes.yaw === 0 && f.eyes.pitch === 0) contact++;
    }
    return { contact: contact / frames, pitch: pitch / frames };
  };
  const flat = run("flat"), neutral = run("neutral");
  expect(flat.contact).toBeLessThan(neutral.contact - 0.2);
  expect(flat.pitch).toBeLessThan(neutral.pitch - 0.05);
});

test("every expression has a face and a bearing", () => {
  expect(Object.keys(MOODS).sort()).toEqual(Object.keys(BEARING).sort());
  expect(Object.keys(MOODS)).toHaveLength(9);
});

test("reduced motion damps head movement", () => {
  const amp = (reduced: boolean) => {
    const b = new Behaviour(seeded(9), reduced);
    let max = 0;
    for (let t = 0; t < 10; t += 0.05) max = Math.max(max, Math.abs(b.update(t).head.roll));
    return max;
  };
  expect(amp(true)).toBeLessThan(amp(false));
});

test("speech events reach listeners until they unsubscribe", () => {
  const seen: string[] = [];
  const stop = onSpeech((e) => seen.push(e.type));
  emitSpeech({ type: "start", text: "Hello there" });
  stop();
  emitSpeech({ type: "end" });
  expect(seen).toEqual(["start"]);
  expect(wordAt("Hello there", 6)).toBe("there");
  expect(wordAt("I'm fine", 0)).toBe("I'm");
});
