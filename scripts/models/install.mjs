import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { modelHome, runtimeDirectory, runtime, register, modelFile } from "./files.mjs";
import { acquire, run, stop } from "./acquire.mjs";

if (process.platform !== "darwin" || process.arch !== "arm64") throw new Error("This runtime is for native Apple Silicon only.");
const archive = path.join(modelHome, "downloads", runtime.archive.filename);
try {
await Promise.all([
  acquire(archive, runtime.archive),
  ...register.models.map((model) => acquire(modelFile(model), model.candidate_artifacts[0])),
]);
await mkdir(runtimeDirectory, { recursive: true });
await run("tar", ["-xzf", archive, "-C", runtimeDirectory]);
await writeFile(path.join(runtimeDirectory, "verified-install.json"), JSON.stringify({
  ...runtime, installed_at: new Date().toISOString(),
}, null, 2) + "\n");
console.log(`Verified native installation: ${runtimeDirectory}`);
} catch (error) {
  stop();
  console.error(error.message);
  process.exitCode = 1;
}
