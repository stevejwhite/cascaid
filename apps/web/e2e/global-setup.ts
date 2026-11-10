import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

export const SPOKEN_QUESTION = "How much do you drink on a typical day?";
export const FAKE_MICROPHONE = fileURLToPath(new URL("../test-results/fake-microphone.wav", import.meta.url));

/** Synthesise the fake-microphone clip on macOS; speech tests skip if it is unavailable. */
export default function setup() {
  mkdirSync(path.dirname(FAKE_MICROPHONE), { recursive: true });
  if (existsSync(FAKE_MICROPHONE)) return;
  try {
    execFileSync("say", ["-v", "Daniel", "-o", FAKE_MICROPHONE, "--file-format=WAVE",
      "--data-format=LEI16@16000", `${SPOKEN_QUESTION} [[slnc 1500]]`]);
  } catch { /* not macOS: the speech test skips */ }
}
