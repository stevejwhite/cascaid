import { readFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { stateFile, root } from "./files.mjs";

try {
  const state = JSON.parse(await readFile(stateFile, "utf8"));
  const command = execFileSync("ps", ["-p", String(state.pid), "-o", "command="], { encoding: "utf8" });
  if (state.root !== root || !command.includes("scripts/models/start.mjs")) throw new Error("Runtime ownership cannot be confirmed");
  process.kill(state.pid, "SIGTERM");
  console.log("Stopping this project's native model servers.");
} catch (error) {
  if (error.code === "ENOENT") console.log("No managed native runtime is running.");
  else { console.error("Could not verify or stop the managed runtime."); process.exitCode = 1; }
}
