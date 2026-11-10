import { execFileSync } from "node:child_process";
import { mkdir, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { root } from "./dev/config.mjs";

function argument(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

function windowsGraphics() {
  if (process.platform !== "win32") return [];
  try {
    const command = [
      "Get-CimInstance Win32_VideoController",
      "Select-Object Name,AdapterRAM,DriverVersion",
      "ConvertTo-Json -Compress"
    ].join(" | ");
    const output = execFileSync("powershell", ["-NoProfile", "-Command", command], {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"]
    }).trim();
    if (!output) return [];
    const parsed = JSON.parse(output);
    return (Array.isArray(parsed) ? parsed : [parsed]).map((gpu) => ({
      name: gpu.Name,
      reported_memory_bytes: gpu.AdapterRAM ?? null,
      driver_version: gpu.DriverVersion ?? null
    }));
  } catch {
    return [{ name: "unavailable", note: "Windows graphics inventory could not be read" }];
  }
}

function macGraphics() {
  if (process.platform !== "darwin") return [];
  try {
    const parsed = JSON.parse(execFileSync("system_profiler", ["SPDisplaysDataType", "-json"], {
      encoding: "utf8", timeout: 10000, stdio: ["ignore", "pipe", "ignore"]
    }));
    // Deliberately exclude attached display identifiers and serial numbers.
    return (parsed.SPDisplaysDataType ?? []).map((gpu) => ({
      name: gpu.sppci_model ?? gpu._name,
      cores: Number(gpu.sppci_cores) || null,
      metal_support: gpu.spdisplays_mtlgpufamilysupport ?? null,
      memory: "unified; shares system RAM"
    }));
  } catch {
    return [{ name: "unavailable", note: "macOS graphics inventory could not be read" }];
  }
}

const cpus = os.cpus();
const inventory = {
  schema_version: 1,
  captured_at: new Date().toISOString(),
  privacy_note: "Hostname, username, IP addresses and device identifiers are intentionally excluded.",
  operating_system: {
    platform: os.platform(),
    release: os.release(),
    architecture: os.arch()
  },
  cpu: {
    model: cpus[0]?.model ?? "unknown",
    logical_processors: cpus.length
  },
  memory: {
    total_bytes: os.totalmem(),
    available_bytes_at_capture: os.freemem()
  },
  accelerators: process.platform === "darwin" ? macGraphics() : windowsGraphics(),
  runtime: {
    node: process.version
  }
};

const output = `${JSON.stringify(inventory, null, 2)}\n`;
const outputPath = argument("--out");
if (outputPath) {
  const resolved = path.resolve(root, outputPath);
  const relation = path.relative(root, resolved);
  if (path.isAbsolute(outputPath) || relation.startsWith("..")) throw new Error("Output path must stay within the project root");
  await mkdir(path.dirname(resolved), { recursive: true });
  await writeFile(resolved, output, "utf8");
  console.log(`Hardware inventory written to ${resolved}`);
} else {
  process.stdout.write(output);
}
