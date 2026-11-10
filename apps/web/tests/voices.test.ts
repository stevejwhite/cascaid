import { expect, test } from "vitest";
import { pickVoice, usableVoices, voiceSex, type VoiceLike } from "../lib/voices";

const v = (name: string, lang: string, localService = true): VoiceLike => ({ name, lang, localService });
const mac = [
  v("Daniel", "en-GB"), v("Flo (English (UK))", "en-GB"), v("Moira", "en-IE"), v("Karen", "en-AU"),
  v("Samantha", "en-US"), v("Bubbles", "en-US"), v("Google UK English Female", "en-GB", false), v("Thomas", "fr-FR"),
];

test("only on-device English voices that are people are usable", () => {
  expect(usableVoices(mac).map((x) => x.name)).toEqual(["Daniel", "Flo (English (UK))", "Moira", "Karen", "Samantha"]);
});

test("a female British character never gets a male voice, and prefers natural voices", () => {
  // Flo is British and female but an older synthesiser voice; Moira is natural and female.
  expect(pickVoice(mac, { sex: "female", accent: "en-GB" })?.name).toBe("Moira");
  expect(pickVoice([v("Daniel", "en-GB"), v("Flo (English (UK))", "en-GB")], { sex: "female", accent: "en-GB" })?.name)
    .toBe("Flo (English (UK))");
});

test("accent decides when sex is not specified, and the choice is stable", () => {
  expect(pickVoice(mac, { accent: "en-GB" })?.name).toBe("Daniel");
  expect(pickVoice(mac, { accent: "en-AU" })?.name).toBe("Karen");
  expect(pickVoice(mac, { sex: "male", accent: "en-US" })?.name).toBe("Daniel");
});

test("unknown voices are neither male nor female, and nothing usable gives undefined", () => {
  expect(voiceSex(v("Mystery", "en-GB"))).toBeUndefined();
  expect(pickVoice([v("Bubbles", "en-US")], { accent: "en-GB" })).toBeUndefined();
});
