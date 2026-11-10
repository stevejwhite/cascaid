// Serve a verified comparison model on loopback. Usage: npm run experiment:start -- qwen3-8b-q4-k-m
import { spawn } from "node:child_process";
import { closeSync, openSync } from "node:fs";
import { mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { verify } from "../models/files.mjs";
import { experiment, experiments, modelPath, root, serverFile, stateFile } from "./files.mjs";

let child, ownsState = false, stopping = false;
async function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  child?.kill("SIGTERM");
  if (ownsState) await rm(stateFile, { force: true });
  process.exitCode = code;
}
process.on("SIGINT", () => void stop());
process.on("SIGTERM", () => void stop());

try {
  const model = experiment(process.argv[2] ?? "qwen3-8b-q4-k-m");
  const file = modelPath(model);
  if (!await verify(file, model).catch(() => false)) throw new Error(`Run npm run experiment:install -- ${model.id} first`);
  const port = experiments.port;
  // Identical runtime settings to the registered model, so comparisons differ only in the model.
  const args = ["--model", file, "--alias", model.alias, "--host", "127.0.0.1", "--port", String(port),
    "--ctx-size", "4096", "--parallel", "1", "--gpu-layers", "99", "--device", "MTL0", "--threads", "4",
    "--offline", "--metrics", "--no-ui", "--no-context-shift", "--flash-attn", "on",
    "--batch-size", "512", "--ubatch-size", "128", "--jinja", "--reasoning", "off", "--reasoning-budget", "0"];
  await mkdir(path.dirname(stateFile), { recursive: true });
  const logFile = path.join(path.dirname(stateFile), "experiment-runtime.log");
  const fd = openSync(logFile, "w", 0o600);
  const started = Date.now();
  child = spawn(serverFile, args, { cwd: root, stdio: ["ignore", fd, fd] });
  closeSync(fd);
  child.once("exit", () => { if (!stopping) void stop(1); });
  const deadline = Date.now() + 180000;
  while (!(await fetch(`http://127.0.0.1:${port}/health`, { signal: AbortSignal.timeout(1000) }).then((r) => r.ok).catch(() => false))) {
    if (stopping || child.exitCode !== null) throw new Error(`Experiment server exited; see ${logFile}`);
    if (Date.now() > deadline) throw new Error(`Experiment server did not start; see ${logFile}`);
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  await writeFile(stateFile, JSON.stringify({ pid: process.pid, server_pid: child.pid, root, port, model: model.id,
    alias: model.alias, revision: model.revision, sha256: model.checksum_sha256, args,
    cold_start_ms: Date.now() - started, started_at: new Date().toISOString() }, null, 2) + "\n", { mode: 0o600 });
  ownsState = true;
  console.log(`${model.id} ready on ${port} (evaluation only). Ctrl-C or npm run experiment:stop stops it.`);
} catch (error) {
  console.error(error.message);
  await stop(1);
}
