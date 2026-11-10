import { readFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { root, stateFile } from "./files.mjs";

try {
  const state = JSON.parse(await readFile(stateFile, "utf8"));
  const command = execFileSync("ps", ["-p", String(state.pid), "-o", "command="], { encoding: "utf8" });
  // Do not signal a recycled PID or another project's process.
  if (state.root !== root || !command.includes("scripts/speech/start.mjs")) throw new Error("Speech runtime ownership cannot be confirmed");
  process.kill(state.pid, "SIGTERM");
  console.log("Stopping this project's speech recognition server.");
} catch (error) {
  if (error.code === "ENOENT") console.log("No managed speech runtime is running.");
  else { console.error("Could not verify or stop the managed speech runtime."); process.exitCode = 1; }
}
