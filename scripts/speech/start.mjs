// Run the verified whisper.cpp server on loopback. Usage: npm run speech:start [-- --model ggml-small.en.bin]
import { spawn } from "node:child_process";
import { closeSync, openSync } from "node:fs";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:net";
import path from "node:path";
import { checksum, verify } from "../models/files.mjs";
import { installRecord, model, modelPath, root, serverFile, speech, stateFile } from "./files.mjs";

const flag = process.argv.indexOf("--model");
const chosen = model(flag >= 0 ? process.argv[flag + 1] : speech.default_model);
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
    server.once("error", () => reject(new Error(`Speech port ${port} is already occupied`)));
    server.listen(port, "127.0.0.1", () => server.close(resolve));
  });
}

try {
  if (process.platform !== "darwin" || process.arch !== "arm64") throw new Error("Native Apple Silicon is required");
  const record = JSON.parse(await readFile(installRecord, "utf8").catch(() => {
    throw new Error("Speech runtime is not installed. Run npm run speech:install first.");
  }));
  if (record.version !== speech.version || record.commit !== speech.commit) throw new Error("Installed speech runtime is not the pinned version; reinstall");
  if (await checksum(serverFile) !== record.binary_sha256) throw new Error("whisper-server binary changed since installation; reinstall");
  const file = modelPath(chosen.filename);
  if (!await verify(file, chosen).catch(() => false)) {
    throw new Error(`Speech model ${chosen.filename} is missing or unverified. Run npm run speech:install -- --models ${chosen.filename}`);
  }
  await free(speech.port);
  await mkdir(path.dirname(stateFile), { recursive: true });
  const logFile = path.join(path.dirname(stateFile), "speech-runtime.log");
  const args = ["--model", file, "--host", "127.0.0.1", "--port", String(speech.port),
    "--threads", String(speech.threads), "--language", speech.language, "--no-timestamps"];
  const fd = openSync(logFile, "w", 0o600);
  const started = Date.now();
  child = spawn(serverFile, args, { cwd: root, stdio: ["ignore", fd, fd] });
  closeSync(fd);
  child.once("exit", () => { if (!stopping) void stop(1); });
  const deadline = Date.now() + 120000;
  while (true) {
    if (stopping || child.exitCode !== null) throw new Error(`whisper-server exited; see ${logFile}`);
    if (Date.now() > deadline) throw new Error(`whisper-server did not become healthy; see ${logFile}`);
    const ok = await fetch(`http://127.0.0.1:${speech.port}/health`, { signal: AbortSignal.timeout(1000) })
      .then((r) => r.ok).catch(() => false);
    if (ok) break;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  await writeFile(stateFile, JSON.stringify({
    pid: process.pid, server_pid: child.pid, root, port: speech.port, version: speech.version,
    commit: speech.commit, binary_sha256: record.binary_sha256, model: chosen.filename,
    model_sha256: chosen.checksum_sha256, args, cold_start_ms: Date.now() - started,
    started_at: new Date().toISOString(), log_file: logFile,
  }, null, 2) + "\n", { mode: 0o600 });
  ownsState = true;
  console.log(`Speech recognition ready on ${speech.port} with ${chosen.filename} (${Date.now() - started} ms). Ctrl-C or npm run speech:stop stops it.`);
} catch (error) {
  console.error(error.message);
  await stop(1);
}
