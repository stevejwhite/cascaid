// Install the pinned HeadTTS server (Kokoro-82M with word timings and visemes) and verified
// model and voice files. Usage: npm run tts:install
import { copyFile, mkdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { checksum } from "../models/files.mjs";
import { acquire, run, stop } from "../models/acquire.mjs";
import { installDirectory, installRecord, modelFile, modelHome, modelUrl, root, tts, voiceFile } from "./files.mjs";

try {
  if (process.platform !== "darwin" || process.arch !== "arm64") throw new Error("This runtime is for native Apple Silicon only.");
  const archive = path.join(modelHome, "downloads", tts.source.filename);
  await acquire(archive, tts.source);
  for (const file of tts.model.files) await acquire(modelFile(file), { ...file, url: modelUrl(file.path) });
  for (const voice of tts.voices) await acquire(voiceFile(voice), { ...voice, url: modelUrl(`voices/${voice.name}.bin`) });
  await rm(installDirectory, { recursive: true, force: true });
  await mkdir(installDirectory, { recursive: true });
  await run("tar", ["-xzf", archive, "-C", installDirectory, "--strip-components", "1"]);
  // Dependencies from HeadTTS's committed lockfile; no install scripts are run.
  await run("npm", ["ci", "--omit=dev", "--ignore-scripts", "--no-audit", "--no-fund", "--prefix", installDirectory]);
  const shim = path.join(installDirectory, "transformers-local.mjs");
  await copyFile(path.join(root, "scripts/tts/transformers-local.mjs"), shim);
  await writeFile(installRecord, JSON.stringify({
    name: tts.name, version: tts.version, commit: tts.commit, source_sha256: tts.source.checksum_sha256,
    model: tts.model.id, model_revision: tts.model.revision, voices: tts.voices.map((v) => v.name),
    lockfile_sha256: await checksum(path.join(installDirectory, "package-lock.json")),
    shim_sha256: await checksum(shim), installed_at: new Date().toISOString(),
  }, null, 2) + "\n");
  console.log(`Verified speech synthesis installation: ${installDirectory}`);
} catch (error) {
  stop();
  console.error(error.message);
  process.exitCode = 1;
}
