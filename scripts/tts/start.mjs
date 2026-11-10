// Run the verified HeadTTS server on loopback. Usage: npm run tts:start
import { spawn } from "node:child_process";
import { closeSync, openSync } from "node:fs";
import { mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { createServer } from "node:net";
import path from "node:path";
import { checksum, verify } from "../models/files.mjs";
import { installDirectory, installRecord, modelFile, modelRoot, root, stateFile, tts, voiceFile, voicePath } from "./files.mjs";

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
    server.once("error", () => reject(new Error(`Speech synthesis port ${port} is already occupied`)));
    server.listen(port, "127.0.0.1", () => server.close(resolve));
  });
}

const synthesize = (input) => fetch(`http://127.0.0.1:${tts.port}/v1/synthesize`, {
  method: "POST", headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ input, voice: tts.voices[0].name, language: tts.language }),
  signal: AbortSignal.timeout(60000),
});

try {
  if (process.platform !== "darwin" || process.arch !== "arm64") throw new Error("Native Apple Silicon is required");
  const record = JSON.parse(await readFile(installRecord, "utf8").catch(() => {
    throw new Error("Speech synthesis is not installed. Run npm run tts:install first.");
  }));
  if (record.commit !== tts.commit || record.model_revision !== tts.model.revision) throw new Error("Installed speech synthesis is not the pinned version; reinstall");
  if (await checksum(path.join(installDirectory, "transformers-local.mjs")) !== record.shim_sha256) throw new Error("HeadTTS model loader changed since installation; reinstall");
  for (const file of tts.model.files) if (!await verify(modelFile(file), file).catch(() => false)) throw new Error(`Kokoro ${file.path} is missing or unverified; run npm run tts:install`);
  for (const voice of tts.voices) if (!await verify(voiceFile(voice), voice).catch(() => false)) throw new Error(`Voice ${voice.name} is missing or unverified; run npm run tts:install`);
  await free(tts.port);
  const stateDir = path.dirname(stateFile);
  await mkdir(stateDir, { recursive: true });
  const config = path.join(stateDir, "headtts-node.json");
  await writeFile(config, JSON.stringify({
    // REST only; no browser calls it directly, so no CORS headers.
    server: { port: tts.port, certFile: null, keyFile: null, websocket: false, rest: true, connectionTimeout: 20000, corsOrigin: "" },
    tts: {
      threads: 1, transformersModule: path.join(installDirectory, "transformers-local.mjs"),
      model: tts.model.id, dtype: tts.dtype, device: tts.device, styleDim: 256, frameRate: 40, audioSampleRate: 24000,
      languages: [tts.language], dictionaryPath: "./dictionaries", voicePath, voices: tts.voices.map((v) => v.name),
      deltaStart: -10, deltaEnd: 10,
      defaults: { voice: tts.voices[0].name, language: tts.language, speed: 1, audioEncoding: "wav" },
    },
    trace: 0,
  }, null, 2));
  const logFile = path.join(stateDir, "tts-runtime.log");
  const args = ["--import", path.join(root, "scripts/tts/loopback.mjs"), "modules/headtts-node.mjs", "--config", config];
  const fd = openSync(logFile, "w", 0o600);
  const started = Date.now();
  child = spawn(process.execPath, args, {
    cwd: installDirectory, stdio: ["ignore", fd, fd],
    env: { ...process.env, HEADTTS_MODEL_ROOT: modelRoot + path.sep, HF_HUB_OFFLINE: "1" },
  });
  closeSync(fd);
  child.once("exit", () => { if (!stopping) void stop(1); });
  // Ready once a first sentence has been synthesised (that also warms the model).
  const deadline = Date.now() + 180000;
  while (true) {
    if (stopping || child.exitCode !== null) throw new Error(`HeadTTS exited; see ${logFile}`);
    if (Date.now() > deadline) throw new Error(`HeadTTS did not become ready; see ${logFile}`);
    const ok = await synthesize("Ready.").then((r) => r.ok).catch(() => false);
    if (ok) break;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  await writeFile(stateFile, JSON.stringify({
    pid: process.pid, server_pid: child.pid, root, port: tts.port, version: tts.version, commit: tts.commit,
    model: tts.model.id, model_revision: tts.model.revision, device: tts.device, dtype: tts.dtype,
    voices: tts.voices.map((v) => v.name), cold_start_ms: Date.now() - started,
    started_at: new Date().toISOString(), log_file: logFile,
  }, null, 2) + "\n", { mode: 0o600 });
  ownsState = true;
  console.log(`Speech synthesis ready on ${tts.port} with Kokoro-82M (${tts.device}, ${Date.now() - started} ms). Ctrl-C or npm run tts:stop stops it.`);
} catch (error) {
  console.error(error.message);
  await stop(1);
}
