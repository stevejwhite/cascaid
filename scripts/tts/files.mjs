import { readFile } from "node:fs/promises";
import path from "node:path";
import { root, modelHome, stateDirectory } from "../models/files.mjs";

export { root, modelHome };
export const tts = JSON.parse(await readFile(path.join(root, "config/tts-runtime.json"), "utf8"));
export const installDirectory = path.join(modelHome, "runtimes", `headtts-${tts.commit.slice(0, 12)}`);
export const installRecord = path.join(installDirectory, "verified-install.json");
// transformers.js looks for <localModelPath>/<model id>/...; voices are HeadTTS .bin files.
export const modelRoot = path.join(modelHome, "models", "transformers", tts.model.revision);
export const modelFile = (file) => path.join(modelRoot, tts.model.id, file.path);
export const voicePath = path.join(modelHome, "models", "kokoro-voices", tts.model.revision);
export const voiceFile = (voice) => path.join(voicePath, `${voice.name}.bin`);
export const stateFile = path.join(stateDirectory, "tts-state.json");
export const modelUrl = (file) => `https://huggingface.co/${tts.model.id}/resolve/${tts.model.revision}/${file}`;
