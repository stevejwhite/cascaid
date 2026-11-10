import { spawn, spawnSync } from "node:child_process";
import { mkdir, writeFile, rm } from "node:fs/promises";
import { openSync, closeSync } from "node:fs";
import { createServer } from "node:net";
import path from "node:path";
import { root, env, runtime, register, modelHome, modelFile, serverFile, stateFile, verify, checksum } from "./files.mjs";

const children = new Set();
let stopping = false;
let ownsState = false;
async function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) child.kill("SIGTERM");
  if (ownsState) await rm(stateFile, { force: true });
  process.exitCode = code;
}
process.on("SIGINT", () => void stop());
process.on("SIGTERM", () => void stop());
async function free(port) {
  await new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", () => reject(new Error(`Model port ${port} is already occupied`)));
    server.listen(port, "127.0.0.1", () => server.close(resolve));
  });
}
async function ready(port, child) {
  const deadline = Date.now() + 120000;
  while (Date.now() < deadline && child.exitCode === null && !stopping) {
    try {
      const response = await fetch(`http://127.0.0.1:${port}/health`, { signal: AbortSignal.timeout(1000) });
      if (response.ok) return;
    } catch { /* still loading */ }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`Model on ${port} did not become healthy; inspect artifacts/m4 runtime logs`);
}

try {
  if (process.platform !== "darwin" || process.arch !== "arm64") throw new Error("Native Apple Silicon is required");
  await free(runtime.generation_port);
  await free(runtime.embedding_port);
  if (!await verify(path.join(modelHome, "downloads", runtime.archive.filename), runtime.archive)) throw new Error("Runtime archive verification failed");
  const version = spawnSync(serverFile, ["--version"], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
  if (version.status !== 0) throw new Error("Installed runtime could not report its version");
  const build = version.stdout + version.stderr;
  if (!build.includes(runtime.commit.slice(0, 7))) throw new Error("Installed binary has an unexpected build identity");
  const directory = path.dirname(stateFile);
  await mkdir(directory, { recursive: true });
  const processes = [];
  for (const model of register.models) {
    const artifact = model.candidate_artifacts[0];
    if (!await verify(modelFile(model), artifact)) throw new Error(`Unverified model artifact: ${model.id}`);
    if (!["generation", "embedding"].includes(model.kind)) throw new Error(`Unsupported model kind: ${model.kind}`);
    const generation = model.kind === "generation";
    const port = generation ? runtime.generation_port : runtime.embedding_port;
    const alias = `${model.upstream_model_id}:${artifact.quantisation}`;
    const args = ["--model", modelFile(model), "--alias", alias, "--host", "127.0.0.1", "--port", String(port),
      // Slots and per-slot context come from config/native-runtime.json; the API checks both.
      "--ctx-size", String(runtime.context_tokens * runtime.parallel_slots),
      "--parallel", String(runtime.parallel_slots), "--gpu-layers", "99", "--device", "MTL0", "--threads", "4",
      "--offline", "--metrics", "--no-ui", "--no-context-shift", "--flash-attn", "on",
      "--cors-origins", "http://127.0.0.1:3105", "--no-cors-credentials"];
    // The host-memory prompt cache otherwise grows to 8 GB by default (seen at 9 GB footprint).
    if (generation) args.push("--batch-size", "512", "--ubatch-size", "128", "--jinja",
      "--reasoning", "off", "--reasoning-budget", "0", "--cache-ram", String(runtime.cache_ram_mib));
    // Qwen3-Embedding uses the last token's state; whole inputs fit in one batch.
    else args.push("--embedding", "--pooling", "last", "--batch-size", "4096", "--ubatch-size", "4096");
    const logFile = path.join(directory, `${model.kind}-runtime.log`);
    const fd = openSync(logFile, "w", 0o600);
    const started = Date.now();
    const child = spawn(serverFile, args, { cwd: root, env, stdio: ["ignore", fd, fd] });
    closeSync(fd);
    children.add(child);
    child.once("error", (error) => { console.error(error.message); void stop(1); });
    child.once("exit", () => { children.delete(child); if (!stopping) void stop(1); });
    await ready(port, child);
    const props = await (await fetch(`http://127.0.0.1:${port}/props`, { signal: AbortSignal.timeout(5000) })).json();
    processes.push({ kind: model.kind, pid: child.pid, port, alias, model_path: modelFile(model),
      sha256: artifact.checksum_sha256, args, cold_start_ms: Date.now() - started,
      build_info: props.build_info, context: props.default_generation_settings?.n_ctx, log_file: logFile });
    console.log(`${model.kind} ready on ${port} (${Date.now() - started} ms)`);
  }
  await writeFile(stateFile, JSON.stringify({ pid: process.pid, root, started_at: new Date().toISOString(),
    runtime, binary_sha256: await checksum(serverFile), processes }, null, 2) + "\n", { mode: 0o600 });
  ownsState = true;
  console.log("Verified local models running. Ctrl-C or npm run models:stop stops only these servers.");
} catch (error) { console.error(error.message); await stop(1); }
