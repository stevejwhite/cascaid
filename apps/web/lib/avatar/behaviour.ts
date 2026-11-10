/**
 * What the character's face and head do from moment to moment, as plain numbers.
 *
 * Deterministic given its random source, so it can be tested without a GPU. The renderer
 * (components/avatar-view.tsx) turns a Frame into blendshape weights and small joint
 * rotations. Angles are in radians; blendshape weights are 0–1.
 */

export type AvatarState = "idle" | "listening" | "thinking" | "speaking";
/** The case's affect-stage expressions (cases.py Expression). */
export type Mood = "neutral" | "warm" | "cheerful" | "sad" | "tearful" | "anxious" | "tense" | "irritable" | "flat";

export interface Angles { pitch: number; yaw: number; roll: number }

export interface Frame {
  /** ARKit and viseme blendshape weights, by name. */
  morphs: Record<string, number>;
  head: Angles;
  /** Where the eyes look, relative to straight ahead (pitch up is positive). */
  eyes: { pitch: number; yaw: number };
  /** Breathing, 0 (out) to 1 (in). */
  breath: number;
}

const DEG = Math.PI / 180;

/** Baseline expressions; small weights, so they colour rather than replace the face. */
export const MOODS: Record<Mood, Record<string, number>> = {
  neutral: {},
  warm: { mouthSmileLeft: 0.5, mouthSmileRight: 0.5, cheekSquintLeft: 0.25, cheekSquintRight: 0.25, browInnerUp: 0.1 },
  cheerful: { mouthSmileLeft: 0.9, mouthSmileRight: 0.9, cheekSquintLeft: 0.5, cheekSquintRight: 0.5, eyeSquintLeft: 0.15, eyeSquintRight: 0.15 },
  sad: { browInnerUp: 0.7, mouthFrownLeft: 0.5, mouthFrownRight: 0.5, eyeSquintLeft: 0.15, eyeSquintRight: 0.15 },
  tearful: { browInnerUp: 0.8, mouthFrownLeft: 0.55, mouthFrownRight: 0.55, eyeSquintLeft: 0.25, eyeSquintRight: 0.25,
    mouthPressLeft: 0.2, mouthPressRight: 0.2, eyeBlinkLeft: 0.1, eyeBlinkRight: 0.1 },
  anxious: { browInnerUp: 0.6, eyeWideLeft: 0.3, eyeWideRight: 0.3, mouthPressLeft: 0.3, mouthPressRight: 0.3, mouthStretchLeft: 0.15, mouthStretchRight: 0.15 },
  tense: { browDownLeft: 0.35, browDownRight: 0.35, mouthPressLeft: 0.6, mouthPressRight: 0.6, eyeSquintLeft: 0.2, eyeSquintRight: 0.2 },
  irritable: { browDownLeft: 0.6, browDownRight: 0.6, mouthPressLeft: 0.45, mouthPressRight: 0.45, noseSneerLeft: 0.25, noseSneerRight: 0.25 },
  // Heavy lids and a slack, slightly downturned mouth.
  flat: { eyeBlinkLeft: 0.3, eyeBlinkRight: 0.3, mouthFrownLeft: 0.2, mouthFrownRight: 0.2, browInnerUp: 0.15 },
};

/** How each expression carries the head and eyes: share of eye contact kept, head lowered
 *  (radians, down is negative) and liveliness of head movement. */
export const BEARING: Record<Mood, { contact: number; pitch: number; liveliness: number }> = {
  neutral: { contact: 1, pitch: 0, liveliness: 1 },
  warm: { contact: 1.1, pitch: 0, liveliness: 1 },
  cheerful: { contact: 1, pitch: 1 * (Math.PI / 180), liveliness: 1.4 },
  sad: { contact: 0.6, pitch: -3 * (Math.PI / 180), liveliness: 0.7 },
  tearful: { contact: 0.45, pitch: -4 * (Math.PI / 180), liveliness: 0.6 },
  anxious: { contact: 0.7, pitch: 0, liveliness: 1.2 },
  tense: { contact: 0.8, pitch: 0, liveliness: 0.6 },
  irritable: { contact: 0.9, pitch: 1 * (Math.PI / 180), liveliness: 0.9 },
  flat: { contact: 0.35, pitch: -5 * (Math.PI / 180), liveliness: 0.4 },
};

/** Every blendshape an expression can use (the renderer resets these each frame). */
export const EXPRESSION_SHAPES = [...new Set(Object.values(MOODS).flatMap((m) => Object.keys(m)))];

// An affect change shows over about a second and a half rather than snapping.
const EXPRESSION_SECONDS = 0.6;

/** How each state moves the eyes and head. */
const STYLE: Record<AvatarState, { contact: number; headAmp: number; gazeAmp: number; nodEvery: [number, number] | null }> = {
  idle: { contact: 0.4, headAmp: 1.5 * DEG, gazeAmp: 8 * DEG, nodEvery: null },
  listening: { contact: 0.85, headAmp: 1.2 * DEG, gazeAmp: 3 * DEG, nodEvery: [4, 8] },
  thinking: { contact: 0.1, headAmp: 1 * DEG, gazeAmp: 4 * DEG, nodEvery: null },
  speaking: { contact: 0.65, headAmp: 2.5 * DEG, gazeAmp: 5 * DEG, nodEvery: null },
};

export class Behaviour {
  private state: AvatarState = "idle";
  private mood: Mood = "neutral";
  private face: Record<string, number> = {};
  private bearing = { ...BEARING.neutral };
  private last = 0;
  private mouth: Record<string, number> = {};
  private nextBlink: number;
  private blinkStart = -1;
  private nextGaze = 0;
  private gaze = { pitch: 0, yaw: 0 };
  private nod = { start: -10, next: Infinity };
  private phases: number[];
  private thinkingSide = 1;

  constructor(private random: () => number = Math.random, private reducedMotion = false) {
    this.nextBlink = 1 + 3 * random();
    this.phases = Array.from({ length: 6 }, () => random() * 2 * Math.PI);
  }

  setState(state: AvatarState, now: number) {
    if (state === this.state) return;
    this.state = state;
    this.nextGaze = now; // react to a change of state straight away
    if (state === "thinking") this.thinkingSide = this.random() < 0.5 ? -1 : 1;
    const every = STYLE[state].nodEvery;
    this.nod.next = every ? now + every[0] + (every[1] - every[0]) * this.random() : Infinity;
  }

  getState(): AvatarState { return this.state; }

  setMood(mood: Mood) { this.mood = mood; }

  /** Viseme weights for this frame, from the lip-sync timeline. */
  setMouth(weights: Record<string, number>) { this.mouth = weights; }

  /** Ease the face and bearing towards the current mood. */
  private settle(now: number) {
    const k = 1 - Math.exp(-Math.max(0, now - this.last) / EXPRESSION_SECONDS);
    this.last = now;
    const target = MOODS[this.mood];
    for (const name of EXPRESSION_SHAPES) {
      const value = (this.face[name] ?? 0) + ((target[name] ?? 0) - (this.face[name] ?? 0)) * k;
      if (Math.abs(value) < 1e-4) delete this.face[name]; else this.face[name] = value;
    }
    const goal = BEARING[this.mood];
    for (const key of ["contact", "pitch", "liveliness"] as const) this.bearing[key] += (goal[key] - this.bearing[key]) * k;
  }

  update(now: number): Frame {
    this.settle(now);
    const style = STYLE[this.state];
    const morphs: Record<string, number> = { ...this.face, ...this.mouth };

    // Blinks: 2–6 s apart; a blink closes over 80 ms, holds 50 ms and opens over 120 ms.
    if (now >= this.nextBlink && this.blinkStart < 0) this.blinkStart = now;
    let blink = 0;
    if (this.blinkStart >= 0) {
      const t = now - this.blinkStart;
      blink = t < 0.08 ? t / 0.08 : t < 0.13 ? 1 : t < 0.25 ? 1 - (t - 0.13) / 0.12 : 0;
      if (t >= 0.25) { this.blinkStart = -1; this.nextBlink = now + 2 + 4 * this.random(); }
    }
    morphs.eyeBlinkLeft = Math.max(morphs.eyeBlinkLeft ?? 0, blink);
    morphs.eyeBlinkRight = Math.max(morphs.eyeBlinkRight ?? 0, blink);

    // Gaze: hold a target, then move; eye contact is the zero target.
    if (now >= this.nextGaze) {
      if (this.state === "thinking") {
        this.gaze = { pitch: (6 + 4 * this.random()) * DEG, yaw: this.thinkingSide * (10 + 6 * this.random()) * DEG };
      } else if (this.random() < Math.min(1, style.contact * this.bearing.contact)) {
        this.gaze = { pitch: 0, yaw: 0 };
      } else {
        this.gaze = { pitch: (this.random() - 0.5) * style.gazeAmp, yaw: (this.random() - 0.5) * 2 * style.gazeAmp };
      }
      this.nextGaze = now + 0.8 + 2.2 * this.random();
    }

    // Head: slow, low-amplitude drift, turned slightly towards where the eyes look.
    const amp = (this.reducedMotion ? style.headAmp * 0.3 : style.headAmp) * this.bearing.liveliness;
    const wave = (i: number, period: number) => Math.sin((2 * Math.PI * now) / period + this.phases[i]);
    const head: Angles = {
      pitch: amp * (0.6 * wave(0, 5.3) + 0.4 * wave(1, 2.9)) + 0.3 * this.gaze.pitch + this.bearing.pitch,
      yaw: amp * (0.6 * wave(2, 6.1) + 0.4 * wave(3, 3.7)) + 0.35 * this.gaze.yaw,
      roll: amp * 0.5 * wave(4, 7.3) + (this.state === "thinking" ? this.thinkingSide * 3 * DEG : 0),
    };

    // Listening: an occasional slow nod.
    if (now >= this.nod.next && STYLE[this.state].nodEvery) {
      this.nod.start = now;
      const [low, high] = STYLE[this.state].nodEvery!;
      this.nod.next = now + low + (high - low) * this.random();
    }
    const sinceNod = now - this.nod.start;
    if (sinceNod < 0.7 && !this.reducedMotion) head.pitch -= 4 * DEG * Math.sin((Math.PI * sinceNod) / 0.7);

    const breath = 0.5 + 0.5 * Math.sin((2 * Math.PI * now) / 4.5 + this.phases[5]);
    return { morphs, head, eyes: { ...this.gaze }, breath };
  }
}
