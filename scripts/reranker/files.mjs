import { readFile } from "node:fs/promises";
import path from "node:path";
import { root, modelHome } from "../models/files.mjs";

export { root, modelHome };
export const configFile = path.join(root, "config/finetune.json");
export const config = JSON.parse(await readFile(configFile, "utf8"));
export const reranker = config.reranker;
export const modelDir = (name) => path.join(modelHome, "models", "reranker", name);
export const stateFile = path.join(root, "artifacts/m4/reranker-state.json");
export const venv = path.join(root, "tools/finetune");
