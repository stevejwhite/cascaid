import { createReadStream } from "node:fs";
import { readFile, stat } from "node:fs/promises";
import { createHash } from "node:crypto";
import os from "node:os";
import path from "node:path";
import { root, environment } from "../dev/config.mjs";

export { root };
export const env = environment();
export const modelHome = env.NATIVE_MODEL_HOME || path.join(os.homedir(), ".cache/psychiatryeduai");
export const runtime = JSON.parse(await readFile(path.join(root, "config/native-runtime.json"), "utf8"));
export const register = JSON.parse(await readFile(path.join(root, "config/model-register.json"), "utf8"));
export const runtimeDirectory = path.join(modelHome, "runtimes", runtime.build);
export const serverFile = path.join(runtimeDirectory, `llama-${runtime.build}`, "llama-server");
export const stateDirectory = env.CASCAID_RUNTIME_STATE_DIR || path.join(root, "artifacts/m4");
export const stateFile = path.join(stateDirectory, "runtime-state.json");
export const modelFile = (model) => path.join(modelHome, "models", model.candidate_artifacts[0].filename);
export async function checksum(file) {
  const hash = createHash("sha256");
  for await (const chunk of createReadStream(file)) hash.update(chunk);
  return hash.digest("hex");
}
export async function verify(file, artifact) {
  return (await stat(file)).size === artifact.size_bytes &&
    await checksum(file) === artifact.checksum_sha256;
}
