/**
 * Approximate lip-sync from text, for voices that report only word boundaries (the
 * browser's on-device voices). Each word becomes a run of Oculus visemes spread over an
 * estimated duration. A neural voice with viseme timings (phase C) replaces the estimate.
 */

export interface Cue { viseme: string; start: number; end: number }

export const VISEMES = ["sil", "PP", "FF", "TH", "DD", "kk", "CH", "SS", "nn", "RR", "aa", "E", "I", "O", "U"] as const;

// Letter groups to visemes, longest first. Rough, but enough to open and close the mouth
// on vowels and to close it on p, b and m.
const RULES: [RegExp, string][] = [
  [/^th/, "TH"], [/^(ch|sh|j)/, "CH"], [/^(ph|f|v)/, "FF"], [/^(p|b|m)/, "PP"],
  [/^(t|d|l)/, "DD"], [/^(k|g|c|q|x)/, "kk"], [/^(s|z)/, "SS"], [/^n/, "nn"], [/^(r|w)/, "RR"],
  [/^(ee|ea|i|y)/, "I"], [/^(oo|u|ou)/, "U"], [/^o/, "O"], [/^e/, "E"], [/^a/, "aa"], [/^h/, "sil"],
];

export function wordVisemes(word: string): string[] {
  const visemes: string[] = [];
  let rest = word.toLowerCase().replace(/[^a-z]/g, "");
  while (rest) {
    const rule = RULES.find(([pattern]) => pattern.test(rest));
    const [pattern, viseme] = rule ?? [/^./, "sil"];
    const taken = rest.match(pattern)![0];
    // Merge repeats so double letters do not stutter.
    if (visemes[visemes.length - 1] !== viseme) visemes.push(viseme);
    rest = rest.slice(taken.length);
  }
  return visemes;
}

/** Seconds a word takes at the default rate, from its length; clamped to sensible bounds. */
export function estimateDuration(word: string, rate = 1): number {
  return Math.min(0.75, Math.max(0.14, (0.065 * word.replace(/[^A-Za-z]/g, "").length) / rate));
}

export function cuesForWord(word: string, start: number, duration = estimateDuration(word)): Cue[] {
  const visemes = wordVisemes(word);
  if (!visemes.length) return [];
  const step = duration / visemes.length;
  return visemes.map((viseme, i) => ({ viseme, start: start + i * step, end: start + (i + 1) * step }));
}

/** Viseme weights at time t, with short cross-fades so the mouth moves smoothly. */
export function weightsAt(cues: readonly Cue[], t: number, fade = 0.05, gain = 0.85): Record<string, number> {
  const weights: Record<string, number> = {};
  for (const cue of cues) {
    if (t < cue.start - fade || t > cue.end + fade) continue;
    const rise = Math.min(1, (t - (cue.start - fade)) / (2 * fade));
    const fall = Math.min(1, ((cue.end + fade) - t) / (2 * fade));
    const w = Math.max(0, Math.min(rise, fall)) * gain;
    if (cue.viseme === "sil") continue;
    const name = `viseme_${cue.viseme}`;
    weights[name] = Math.max(weights[name] ?? 0, w);
  }
  return weights;
}
