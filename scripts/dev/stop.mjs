import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { root } from "./config.mjs";

const state = path.join(root, "artifacts/dev/supervisor.json");
if (existsSync(state)) {
  const { pid, root: recordedRoot } = JSON.parse(readFileSync(state, "utf8"));
  try {
    // Do not signal a recycled PID or another project's process.
    const command = execFileSync("ps", ["-p", String(pid), "-o", "command="], { encoding: "utf8" });
    if (recordedRoot === root && command.includes("scripts/dev/start.mjs")) process.kill(pid, "SIGTERM");
  } catch { /* supervisor is already stopped */ }
}
