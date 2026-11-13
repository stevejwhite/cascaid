import { cp, mkdir, readdir, readFile, writeFile, lstat, access } from "node:fs/promises";
import { createReadStream } from "node:fs";
import { createHash } from "node:crypto";
import path from "node:path";
import { sourceRoot } from "./config.mjs";
import { command } from "./processes.mjs";

// Copy only deployment inputs. Never copy .env, sessions, recordings, evaluations,
// repository history, downloaded source corpora or the developer's build/venvs.
export const inputs = ["package.json", "package-lock.json", "config", "prompts", "scripts",
  "apps/web", "services/api/pyproject.toml", "services/api/uv.lock", "services/api/src",
  "tools/finetune/pyproject.toml", "tools/finetune/uv.lock", "data/cases",
  "data/catalogue", "data/training/topics", "data/training/tone"];
const excluded = new Set(["node_modules", ".next", ".venv", "__pycache__", "test-results",
  "playwright-report", "coverage", ".DS_Store"]);
export const copyable = (name) => !excluded.has(name) && !name.startsWith(".env") &&
  !name.endsWith(".tsbuildinfo") && !name.endsWith(".pyc") && !name.endsWith(".log");

export async function hashFile(file) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(file)) hash.update(chunk);
  return hash.digest("hex");
}

async function files(directory, relative = "") {
  const result = [];
  for (const entry of await readdir(path.join(directory, relative), { withFileTypes: true })) {
    if (!copyable(entry.name)) continue;
    const name = path.join(relative, entry.name);
    if (entry.isSymbolicLink()) throw new Error(`Release input cannot be a symlink: ${name}`);
    if (entry.isDirectory()) result.push(...await files(directory, name));
    else if (entry.isFile()) result.push(name);
  }
  return result.sort();
}

export const configDigest = (c) => createHash("sha256").update(JSON.stringify({
  release: c.release, persistent: c.persistent, modelHome: c.modelHome,
  webPort: c.webPort, apiPort: c.apiPort,
})).digest("hex");

export async function snapshot(c) {
  if (c.release === sourceRoot) throw new Error("Preparation must target a new directory outside this checkout");
  await mkdir(path.dirname(c.release), { recursive: true, mode: 0o700 });
  // A failed preparation is deliberately not overwritten. Choose a new release name.
  await mkdir(c.release, { mode: 0o700 });
  for (const relative of inputs) {
    const origin = path.join(sourceRoot, relative);
    await cp(origin, path.join(c.release, relative), { recursive: true, filter: async (src) => {
      if (!copyable(path.basename(src))) return false;
      if ((await lstat(src)).isSymbolicLink()) throw new Error(`Symlink in release input: ${src}`);
      return true;
    } });
  }
}

export async function prepare(c) {
  await snapshot(c);
  const options = { cwd: c.release, env: c.env };
  // Dependency acquisition belongs only to preparation. Existing npm/uv caches
  // are sufficient for offline preparation; no model acquisition is attempted.
  await command("npm", ["ci", "--offline", "--include=dev", "--no-audit", "--no-fund"], options);
  for (const project of ["services/api", "tools/finetune"]) {
    await command("uv", ["sync", "--offline", "--project", project, "--locked"], options);
  }
  await command("npm", ["run", "build:web"], options);
  await access(path.join(c.release, "apps/web/.next/BUILD_ID"));
  const hashes = {};
  for (const file of await files(c.release)) hashes[file] = await hashFile(path.join(c.release, file));
  await writeFile(path.join(c.release, "production-release.json"), JSON.stringify({
    prepared_at: new Date().toISOString(), node: process.version, config: configDigest(c),
    build_id: (await readFile(path.join(c.release, "apps/web/.next/BUILD_ID"), "utf8")).trim(), hashes,
  }, null, 2) + "\n", { mode: 0o600 });
}

export async function verifyRelease(c) {
  const manifest = JSON.parse(await readFile(path.join(c.release, "production-release.json"), "utf8")
    .catch(() => { throw new Error("Release is not prepared; run production:prepare first"); }));
  for (const directory of [c.release, path.join(c.release, "apps/web")]) {
    if ((await readdir(directory)).some((name) => name.startsWith(".env"))) {
      throw new Error("A release must not contain .env files; use the external production configuration");
    }
  }
  if (manifest.config !== configDigest(c) || manifest.node !== process.version) {
    throw new Error("Release configuration or Node version changed; prepare a new release");
  }
  const current = (await files(c.release)).filter((file) => file !== "production-release.json");
  if (JSON.stringify(current) !== JSON.stringify(Object.keys(manifest.hashes).sort())) {
    throw new Error("Release input file inventory changed; prepare a new release");
  }
  for (const file of current) {
    if (await hashFile(path.join(c.release, file)) !== manifest.hashes[file]) {
      throw new Error(`Prepared release changed: ${file}; prepare a new release`);
    }
  }
  if ((await readFile(path.join(c.release, "apps/web/.next/BUILD_ID"), "utf8")).trim() !== manifest.build_id) {
    throw new Error("Prepared Next build changed");
  }
  for (const file of ["node_modules/next/dist/bin/next", "services/api/.venv/bin/uvicorn",
    "tools/finetune/.venv/bin/mlx_lm.server"]) await access(path.join(c.release, file));
  return manifest;
}
