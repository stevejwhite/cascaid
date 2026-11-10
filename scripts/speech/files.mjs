import { readFile } from "node:fs/promises";
import path from "node:path";
import { root, modelHome, stateDirectory } from "../models/files.mjs";

export { root, modelHome };
export const speech = JSON.parse(await readFile(path.join(root, "config/speech-runtime.json"), "utf8"));
export const installDirectory = path.join(modelHome, "runtimes", `whisper.cpp-${speech.version}`);
export const serverFile = path.join(installDirectory, "whisper-server");
export const installRecord = path.join(installDirectory, "verified-install.json");
export const stateFile = path.join(stateDirectory, "speech-state.json");
export const modelPath = (filename) => path.join(modelHome, "models", filename);
export function model(filename = speech.default_model) {
  const found = speech.models.find((m) => m.filename === filename);
  if (!found) throw new Error(`Unregistered speech model: ${filename}`);
  return found;
}
