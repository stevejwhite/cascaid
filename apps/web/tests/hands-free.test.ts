import { expect, test } from "vitest";
import { isEcho } from "../lib/hands-free";

test("the character's own voice picked up by the microphone is recognised as echo", () => {
  const line = "About a litre of vodka a day, sometimes more at the weekend.";
  expect(isEcho("a litre of vodka a day sometimes more", line)).toBe(true);
  expect(isEcho("How do you feel about cutting down?", line)).toBe(false);
  expect(isEcho("vodka", line)).toBe(false); // too short to judge
  expect(isEcho("anything", undefined)).toBe(false);
});
