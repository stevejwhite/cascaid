import { access, readFile, stat, mkdir, realpath } from "node:fs/promises";
import path from "node:path";
import { freePorts } from "./processes.mjs";
import { hashFile, verifyRelease } from "./release.mjs";

export async function verifyAssets(c) {
  const json = async (name) => JSON.parse(await readFile(path.join(c.release, "config", name), "utf8"));
  const native = await json("native-runtime.json"), register = await json("model-register.json");
  const speech = await json("speech-runtime.json"), tts = await json("tts-runtime.json");
  const student = (await json("finetune.json")).student;
  const expected = [
    [path.join(c.modelHome, "downloads", native.archive.filename), native.archive],
    ...register.models.map((m) => [path.join(c.modelHome, "models", m.candidate_artifacts[0].filename), m.candidate_artifacts[0]]),
    [path.join(c.modelHome, "models", speech.default_model), speech.models.find((m) => m.filename === speech.default_model)],
    ...student.files.map((f) => [path.join(c.modelHome, "models/student", student.name, f.path), f]),
    ...tts.model.files.map((f) => [path.join(c.modelHome, "models/transformers", tts.model.revision, tts.model.id, f.path), f]),
    ...tts.voices.map((v) => [path.join(c.modelHome, "models/kokoro-voices", tts.model.revision, `${v.name}.bin`), v]),
  ];
  for (const [file, artifact] of expected) {
    if (await stat(file).then((s) => s.size).catch(() => -1) !== artifact.size_bytes ||
      await hashFile(file) !== artifact.checksum_sha256) {
      throw new Error(`Missing or unverified installed asset: ${path.basename(file)}. Install registered assets separately; startup never downloads them.`);
    }
  }
  await access(path.join(c.modelHome, "runtimes", native.build, `llama-${native.build}`, "llama-server"));
  const speechDir = path.join(c.modelHome, "runtimes", `whisper.cpp-${speech.version}`);
  const sr = JSON.parse(await readFile(path.join(speechDir, "verified-install.json"), "utf8"));
  if (sr.commit !== speech.commit || sr.version !== speech.version ||
    await hashFile(path.join(speechDir, "whisper-server")) !== sr.binary_sha256) throw new Error("Speech installation changed");
  const ttsDir = path.join(c.modelHome, "runtimes", `headtts-${tts.commit.slice(0, 12)}`);
  const tr = JSON.parse(await readFile(path.join(ttsDir, "verified-install.json"), "utf8"));
  if (tr.commit !== tts.commit || tr.model_revision !== tts.model.revision ||
    await hashFile(path.join(ttsDir, "transformers-local.mjs")) !== tr.shim_sha256) throw new Error("TTS installation changed");
}

export async function directories(c) {
  for (const directory of [c.persistent, c.stateDir, c.logDir, c.env.SESSIONS_PATH,
    c.env.CLASSIFIER_CACHE, path.join(c.persistent, "database")]) {
    await mkdir(directory, { recursive: true, mode: 0o700 });
    if (await realpath(directory) !== directory) throw new Error(`Private directory must not use symlinks: ${directory}`);
    const info = await stat(directory);
    if (info.uid !== process.getuid() || info.mode & 0o077) throw new Error(`Private directory must be owned by this account and mode 700: ${directory}`);
  }
}

export async function preflight(c) {
  if (process.platform !== "darwin" || process.arch !== "arm64") throw new Error("Production requires native Apple Silicon macOS");
  // Fixed registered model ports intentionally enforce mutually exclusive use.
  await freePorts(c.ports);
  await verifyRelease(c);
  await verifyAssets(c);
  await directories(c);
  return { status: "passed", profile: c.profile, ports: c.ports, release: c.release };
}
