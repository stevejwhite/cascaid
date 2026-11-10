// Install the topic reranker (docs/RERANKER-PLAN.md) and pin its files by checksum in
// config/finetune.json. Usage: npm run reranker:install [-- qwen3-reranker-0.6b]
// The weights come from the base model pinned in config/finetune.json (downloaded and checked
// against Hugging Face's SHA-256 records by tools/finetune/download.py).
import { execFileSync } from "node:child_process";
import { cp, mkdir, readdir, rm, stat, writeFile } from "node:fs/promises";
import path from "node:path";
import { checksum } from "../models/files.mjs";
import { config, configFile, modelDir, root, venv } from "./files.mjs";

const name = process.argv[2] || "qwen3-reranker-0.6b";
try {
  const base = config.base_models[name];
  if (!base) throw new Error(`No base model ${name} in config/finetune.json`);
  const out = execFileSync("uv", ["run", "--project", venv, "--locked", "python", "-I",
    path.join(venv, "download.py"), name], { cwd: root, encoding: "utf8" });
  const source = /^Verified .* in (.+)$/m.exec(out)?.[1];
  if (!source) throw new Error("The download did not report a verified directory");
  const target = modelDir(name);
  await rm(target, { recursive: true, force: true });
  await mkdir(path.dirname(target), { recursive: true });
  await cp(source, target, { recursive: true });
  const files = [];
  for (const entry of (await readdir(target, { recursive: true, withFileTypes: true })).sort((a, b) => a.name.localeCompare(b.name))) {
    if (!entry.isFile()) continue;
    const file = path.join(entry.parentPath, entry.name);
    files.push({ path: path.relative(target, file), size_bytes: (await stat(file)).size, checksum_sha256: await checksum(file) });
  }
  files.sort((a, b) => a.path.localeCompare(b.path));
  const weights = files.find((f) => f.path === "model.safetensors");
  config.reranker = { name, repo: base.repo, revision: base.revision, licence: base.licence, port: 8185,
    weights_sha256: weights.checksum_sha256, files };
  await writeFile(configFile, JSON.stringify(config, null, 2) + "\n");
  console.log(`Installed ${name} (${base.repo}@${base.revision.slice(0, 12)}); pinned in config/finetune.json`);
} catch (error) {
  console.error(error.message);
  process.exitCode = 1;
}
