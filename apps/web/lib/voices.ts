/** Choose an on-device voice for a character from its voice hint. */

export interface VoiceHint {
  sex?: "female" | "male" | null;
  age?: "young" | "adult" | "older";
  accent?: string;
}

/** The parts of SpeechSynthesisVoice this module uses (eases testing). */
export interface VoiceLike {
  name: string;
  lang: string;
  localService: boolean;
  voiceURI?: string;
}

// The Web Speech API does not report a voice's sex, so known macOS and iOS voice names are
// listed here. Unlisted voices count as unknown and rank below a listed match.
const SEX: Record<string, "female" | "male"> = {
  Daniel: "male", Oliver: "male", Arthur: "male", Aman: "male", Rishi: "male", Alex: "male",
  Tom: "male", Aaron: "male", Evan: "male", Nathan: "male", Fred: "male", Ralph: "male",
  Junior: "male", Albert: "male", Eddy: "male", Reed: "male", Rocko: "male", Grandpa: "male",
  Gordon: "male", Lee: "male",
  Moira: "female", Karen: "female", Samantha: "female", Tessa: "female", Tara: "female",
  Kate: "female", Serena: "female", Martha: "female", Fiona: "female", Ava: "female",
  Allison: "female", Susan: "female", Victoria: "female", Zoe: "female", Joelle: "female",
  Nicky: "female", Veena: "female", Kathy: "female", Flo: "female", Sandy: "female",
  Shelley: "female", Grandma: "female", Catherine: "female", Isha: "female",
};
// Sound effects rather than speakers.
const NOVELTY = new Set(["Bad News", "Bahh", "Bells", "Boing", "Bubbles", "Cellos", "Wobble",
  "Good News", "Jester", "Organ", "Superstar", "Trinoids", "Whisper", "Zarvox"]);
// Older synthesiser voices: usable, but less natural than the main system voices.
const ROBOTIC = new Set(["Eddy", "Flo", "Grandma", "Grandpa", "Reed", "Rocko", "Sandy",
  "Shelley", "Fred", "Ralph", "Junior", "Albert", "Kathy"]);

export function baseName(voice: VoiceLike): string {
  return voice.name.split(" (")[0].trim();
}

export function voiceSex(voice: VoiceLike): "female" | "male" | undefined {
  return SEX[baseName(voice)];
}

/** On-device English voices that are people rather than sound effects. */
export function usableVoices(voices: readonly VoiceLike[]): VoiceLike[] {
  return voices.filter((v) => v.localService && v.lang.toLowerCase().startsWith("en")
    && !NOVELTY.has(baseName(v)));
}

function score(voice: VoiceLike, hint: VoiceHint): number {
  const sex = voiceSex(voice);
  const name = baseName(voice);
  const lang = voice.lang.replace("_", "-");
  let points = 0;
  if (hint.sex) points += sex === hint.sex ? 8 : sex ? -8 : 0;
  if (hint.accent && lang.toLowerCase() === hint.accent.toLowerCase()) points += 3;
  // Naturalness outweighs an exact accent match (a natural Irish voice beats a robotic British one).
  if (ROBOTIC.has(name)) points -= 4;
  if (hint.age === "older" && (name === "Grandma" || name === "Grandpa")) points += 2;
  return points;
}

/** The best match for the hint; ties keep the browser's order, so the choice is stable. */
export function pickVoice(voices: readonly VoiceLike[], hint: VoiceHint): VoiceLike | undefined {
  let best: VoiceLike | undefined;
  let bestScore = -Infinity;
  for (const voice of usableVoices(voices)) {
    const points = score(voice, hint);
    if (points > bestScore) { best = voice; bestScore = points; }
  }
  return best;
}
