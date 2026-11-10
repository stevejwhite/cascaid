// Install a trained, quantised student (tools/finetune/fuse.sh output) and pin it by checksum
// in config/finetune.json. Usage: npm run student:install -- student-0.6b-v3 [qwen3-0.6b]
// The base model is taken from the second argument, else from the run's adapter config.
// The weights stay on this machine: they were trained partly on local session transcripts.
import { cp, mkdir, readdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { checksum } from "../models/files.mjs";
import { config, configFile, modelDir, root } from "./files.mjs";

const run = process.argv[2];
async function baseOf(runDir) {
  if (process.argv[3]) return process.argv[3];
  const adapter = JSON.parse(await readFile(path.join(runDir, "adapter", "adapter_config.json"), "utf8"));
  // mlx_lm records the model path it trained on: .../hf/Qwen3-1.7B-<revision>
  const match = /Qwen3-([0-9.]+B)-/i.exec(adapter.model ?? "");
  if (!match) throw new Error("Cannot tell the base model; pass it: npm run student:install -- <run> qwen3-1.7b");
  return `qwen3-${match[1].toLowerCase()}`;
}
try {
  if (!run) throw new Error("Usage: npm run student:install -- <run name>");
  const source = path.join(root, "artifacts/finetune/runs", run, "fused-q4");
  await stat(source).catch(() => { throw new Error(`No quantised student at ${source}; run tools/finetune/fuse.sh first`); });
  const target = modelDir(run);
  await rm(target, { recursive: true, force: true });
  await mkdir(path.dirname(target), { recursive: true });
  await cp(source, target, { recursive: true });
  const files = [];
  for (const name of (await readdir(target)).sort()) {
    const file = path.join(target, name);
    files.push({ path: name, size_bytes: (await stat(file)).size, checksum_sha256: await checksum(file) });
  }
  const weights = files.find((f) => f.path.endsWith(".safetensors"));
  const format = (await readFile(path.join(root, "services/api/src/psychiatry_api/finetune/format.py"), "utf8"))
    .match(/FORMAT_VERSION = "([^"]+)"/)[1];
  config.student = {
    name: run, base: await baseOf(path.join(root, "artifacts/finetune/runs", run)), format_version: format, quantisation: "4-bit",
    port: config.student?.port ?? 8184, weights_sha256: weights.checksum_sha256, files,
    note: "Trained by tools/finetune on authored lines (teacher-completed) and local session turns; the weights are not committed.",
  };
  await writeFile(configFile, JSON.stringify(config, null, 2) + "\n");
  console.log(`Installed ${run} (${format}); pinned in config/finetune.json`);
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
