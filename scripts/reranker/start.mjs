// Serve the installed topic reranker on loopback with MLX. Usage: npm run reranker:start
import { spawn } from "node:child_process";
import { closeSync, openSync } from "node:fs";
import { mkdir, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:net";
import path from "node:path";
import { verify } from "../models/files.mjs";
import { modelDir, reranker, root, stateFile, venv } from "./files.mjs";

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
    server.once("error", () => reject(new Error(`Reranker port ${port} is already occupied`)));
    server.listen(port, "127.0.0.1", () => server.close(resolve));
  });
}

try {
  if (process.platform !== "darwin" || process.arch !== "arm64") throw new Error("Apple Silicon is required (MLX)");
  if (!reranker) throw new Error("No reranker installed: run npm run reranker:install");
  const dir = modelDir(reranker.name);
  for (const file of reranker.files) {
    if (!await verify(path.join(dir, file.path), file).catch(() => false)) {
      throw new Error(`Reranker file ${file.path} is missing or changed; run npm run reranker:install`);
    }
  }
  await free(reranker.port);
  await mkdir(path.dirname(stateFile), { recursive: true });
  const logFile = path.join(path.dirname(stateFile), "reranker-runtime.log");
  const fd = openSync(logFile, "w", 0o600);
  const started = Date.now();
  child = spawn("uv", ["run", "--project", venv, "--locked", "python", path.join(venv, "rerank_server.py"), dir,
    "--port", String(reranker.port)], { cwd: root, stdio: ["ignore", fd, fd] });
  closeSync(fd);
  child.once("exit", () => { if (!stopping) void stop(1); });
  const base = `http://127.0.0.1:${reranker.port}`;
  const deadline = Date.now() + 120000;
  while (true) {
    if (stopping || child.exitCode !== null) throw new Error(`Reranker server exited; see ${logFile}`);
    if (Date.now() > deadline) throw new Error(`Reranker server did not become ready; see ${logFile}`);
    const ok = await fetch(`${base}/health`, { signal: AbortSignal.timeout(1000) }).then((r) => r.ok).catch(() => false);
    if (ok) break;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  await writeFile(stateFile, JSON.stringify({
    pid: process.pid, server_pid: child.pid, root, port: reranker.port, model: reranker.name,
    revision: reranker.revision, weights_sha256: reranker.weights_sha256,
    cold_start_ms: Date.now() - started, started_at: new Date().toISOString(), log_file: logFile,
  }, null, 2) + "\n", { mode: 0o600 });
  ownsState = true;
  console.log(`Topic reranker ready on ${reranker.port}: ${reranker.name} (${Date.now() - started} ms). Ctrl-C or npm run reranker:stop stops it.`);
} catch (error) {
  console.error(error.message);
  await stop(1);
}
