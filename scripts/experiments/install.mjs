// Download a pinned comparison model. Usage: npm run experiment:install -- qwen3-8b-q4-k-m
import { acquire, stop } from "../models/acquire.mjs";
import { experiment, modelPath } from "./files.mjs";

try {
  const model = experiment(process.argv[2] ?? "qwen3-8b-q4-k-m");
  await acquire(modelPath(model), model);
  console.log(`Verified ${model.filename}. It is for evaluation only.`);
} catch (error) {
  stop();
  console.error(error.message);
  process.exitCode = 1;
}
