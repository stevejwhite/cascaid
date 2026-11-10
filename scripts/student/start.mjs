// Serve the installed student interpreter on loopback with mlx_lm.server. Usage: npm run student:start
import { spawn } from "node:child_process";
import { closeSync, openSync } from "node:fs";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:net";
import path from "node:path";
import { verify } from "../models/files.mjs";
import { modelDir, root, stateFile, student, venv } from "./files.mjs";

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

async function free(port) {
  await new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", () => reject(new Error(`Student port ${port} is already occupied`)));
    server.listen(port, "127.0.0.1", () => server.close(resolve));
  });
}

try {
  if (process.platform !== "darwin" || process.arch !== "arm64") throw new Error("Apple Silicon is required (MLX)");
  if (!student) throw new Error("No student installed: run npm run student:install -- <run>");
  const dir = modelDir(student.name);
  for (const file of student.files) {
    if (!await verify(path.join(dir, file.path), file).catch(() => false)) {
      throw new Error(`Student file ${file.path} is missing or changed; run npm run student:install -- ${student.name}`);
    }
  }
  await free(student.port);
  await mkdir(path.dirname(stateFile), { recursive: true });
  const logFile = path.join(path.dirname(stateFile), "student-runtime.log");
  const fd = openSync(logFile, "w", 0o600);
  const started = Date.now();
  const production = process.env.CASCAID_PRODUCTION_ACTIVE === "1";
  child = spawn(production ? path.join(venv, ".venv/bin/mlx_lm.server") : "uv",
    [...(production ? [] : ["run", "--project", venv, "--locked", "mlx_lm.server"]), "--model", dir,
    "--host", "127.0.0.1", "--port", String(student.port), "--allowed-origins", "http://127.0.0.1",
    "--temp", "0", "--max-tokens", "160", "--log-level", "WARNING"], { cwd: root, stdio: ["ignore", fd, fd] });
  closeSync(fd);
  child.once("exit", () => { if (!stopping) void stop(1); });
  const base = `http://127.0.0.1:${student.port}`;
  const deadline = Date.now() + 120000;
  while (true) {
    if (stopping || child.exitCode !== null) throw new Error(`Student server exited; see ${logFile}`);
    if (Date.now() > deadline) throw new Error(`Student server did not become ready; see ${logFile}`);
    const ok = await fetch(`${base}/health`, { signal: AbortSignal.timeout(1000) }).then((r) => r.ok).catch(() => false);
    if (ok) break;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  // Warm up (loads kernels) so the first real turn is not slow.
  const warm = await fetch(`${base}/v1/chat/completions`, { method: "POST", headers: { "Content-Type": "application/json" },
    signal: AbortSignal.timeout(60000),
    body: JSON.stringify({ messages: [{ role: "user", content: "Ready?" }], max_tokens: 4,
      chat_template_kwargs: { enable_thinking: false } }) });
  if (!warm.ok) throw new Error("Student warm-up failed");
  await writeFile(stateFile, JSON.stringify({
    pid: process.pid, server_pid: child.pid, root, port: student.port, model: student.name,
    format_version: student.format_version, weights_sha256: student.weights_sha256,
    cold_start_ms: Date.now() - started, started_at: new Date().toISOString(), log_file: logFile,
  }, null, 2) + "\n", { mode: 0o600 });
  ownsState = true;
  console.log(`Student interpreter ready on ${student.port}: ${student.name} (${Date.now() - started} ms). Ctrl-C or npm run student:stop stops it.`);
} catch (error) {
  console.error(error.message);
  await stop(1);
}
