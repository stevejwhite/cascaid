import { readFile } from "node:fs/promises";
import path from "node:path";
import { root, modelHome, serverFile, runtime } from "../models/files.mjs";

export { root, modelHome, serverFile, runtime };
export const experiments = JSON.parse(await readFile(path.join(root, "config/experiment-models.json"), "utf8"));
export const stateFile = path.join(root, "artifacts/m4/experiment-state.json");
export const modelPath = (m) => path.join(modelHome, "experiments", m.filename);
export function experiment(id) {
  const found = experiments.models.find((m) => m.id === id);
  if (!found) throw new Error(`Unknown experiment model ${id}; see config/experiment-models.json`);
  return found;
}
