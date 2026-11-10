import { readFile } from "node:fs/promises";
import path from "node:path";
import { root, modelHome, stateDirectory } from "../models/files.mjs";

export { root, modelHome };
export const configFile = path.join(root, "config/finetune.json");
export const config = JSON.parse(await readFile(configFile, "utf8"));
export const student = config.student;
export const modelDir = (name) => path.join(modelHome, "models", "student", name);
export const stateFile = path.join(stateDirectory, "student-state.json");
export const venv = path.join(root, "tools/finetune");
