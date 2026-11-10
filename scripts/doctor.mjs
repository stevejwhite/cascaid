import { spawnSync } from "node:child_process";
import os from "node:os";

function probe(command, args) {
  const result = spawnSync(command, args, { encoding: "utf8", timeout: 5000 });
  return { available: result.status === 0, version: result.status === 0 ? result.stdout.trim() : null };
}

const python = probe("uv", ["run", "--no-project", "--offline", "--python", "3.12", "python", "--version"]);
const inference = probe("llama-server", ["--version"]);
const report = {
  capturedAt: new Date().toISOString(),
  platform: process.platform,
  architecture: process.arch,
  cpu: os.cpus()[0]?.model,
  ramGiB: os.totalmem() / 1024 ** 3,
  node: process.version,
  python312ViaUv: python,
  llamaServer: inference,
  note: "Tool availability only. Application services and model quality are evaluated separately (docs/CASC-POC-PLAN.md)."
};
console.log(JSON.stringify(report, null, 2));
