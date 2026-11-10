import { readFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { root, stateFile } from "./files.mjs";

try {
  const state = JSON.parse(await readFile(stateFile, "utf8"));
  const command = execFileSync("ps", ["-p", String(state.pid), "-o", "command="], { encoding: "utf8" });
  if (state.root !== root || !command.includes("scripts/experiments/start.mjs")) throw new Error("ownership");
  process.kill(state.pid, "SIGTERM");
  console.log("Stopping the experiment model server.");
} catch (error) {
  if (error.code === "ENOENT") console.log("No experiment model server is running.");
  else { console.error("Could not verify or stop the experiment server."); process.exitCode = 1; }
}
