import { mkdir, rename, access, stat, readFile, appendFile, rm } from "node:fs/promises";
import { spawn } from "node:child_process";
import path from "node:path";
import { verify } from "./files.mjs";

// Shared by the model and speech installers: checksum-verified, resumable downloads.
const children = new Set();
let stopping = false;
export function stop() {
  stopping = true;
  for (const child of children) child.kill("SIGTERM");
}
process.on("SIGINT", stop);
process.on("SIGTERM", stop);

export function run(command, args) {
  if (stopping) return Promise.reject(new Error("Installation cancelled"));
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: "inherit" });
    children.add(child);
    child.once("error", reject);
    child.once("exit", (code) => {
      children.delete(child);
      code === 0 ? resolve() : reject(new Error(`${command} exited ${code}`));
    });
  });
}
export async function acquire(file, artifact) {
  await mkdir(path.dirname(file), { recursive: true });
  try { if (await verify(file, artifact)) { console.log(`Verified ${path.basename(file)}`); return; } }
  catch (error) { if (error.code !== "ENOENT") throw error; }
  try { await access(file); throw new Error(`Existing file failed verification: ${file}`); }
  catch (error) { if (error.code !== "ENOENT") throw error; }
  console.log(`Acquiring pinned ${path.basename(file)} (${artifact.size_bytes} bytes)`);
  if (artifact.size_bytes > 100_000_000) {
    // Keep any already downloaded prefix; bounded ranges avoid a slow single CDN connection.
    const prefix = await stat(`${file}.partial`).then((s) => s.size).catch((e) => { if (e.code === "ENOENT") return 0; throw e; });
    if (prefix > artifact.size_bytes) throw new Error("Partial file exceeds registered artifact size");
    const parts = `${file}.parts-${prefix}`;
    await mkdir(parts, { recursive: true });
    const chunkSize = 32 * 1024 * 1024;
    const count = Math.ceil((artifact.size_bytes - prefix) / chunkSize);
    let next = 0;
    async function worker() {
      while (next < count) {
        const index = next++;
        const start = prefix + index * chunkSize;
        const end = Math.min(artifact.size_bytes - 1, start + chunkSize - 1);
        const part = path.join(parts, String(index));
        const expected = end - start + 1;
        if (await stat(part).then((s) => s.size === expected).catch(() => false)) continue;
        await run("curl", ["--fail", "--location", "--silent", "--show-error", "--retry", "3",
          "--range", `${start}-${end}`, "--max-filesize", String(Math.max(expected, 65536)),
          "--max-time", "600", "--output", `${part}.partial`, artifact.source || artifact.url]);
        if ((await stat(`${part}.partial`)).size !== expected) throw new Error("Download server returned an invalid byte range");
        await rename(`${part}.partial`, part);
      }
    }
    await Promise.all(Array.from({ length: 6 }, worker));
    for (let index = 0; index < count; index++) await appendFile(`${file}.partial`, await readFile(path.join(parts, String(index))));
    if (!await verify(`${file}.partial`, artifact)) throw new Error(`Checksum/size mismatch: ${file}.partial`);
    await rm(parts, { recursive: true });
  } else {
    await run("curl", ["--fail", "--location", "--silent", "--show-error", "--retry", "3",
      "--continue-at", "-", "--max-time", "3600", "--output", `${file}.partial`, artifact.source || artifact.url]);
  }
  if (!await verify(`${file}.partial`, artifact)) throw new Error(`Checksum/size mismatch: ${file}.partial`);
  await rename(`${file}.partial`, file);
  console.log(`Verified ${path.basename(file)}`);
}
