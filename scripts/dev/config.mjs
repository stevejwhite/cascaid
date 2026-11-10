import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { parseEnv } from "node:util";

export const root = fileURLToPath(new URL("../../", import.meta.url));
export function environment({ create = false } = {}) {
  // Production supplies a complete, validated environment. Never merge the checkout's
  // development .env back over it in a nested model launcher.
  if (process.env.CASCAID_PRODUCTION_ACTIVE === "1") return { ...process.env };
  const file = path.join(root, ".env");
  if (!existsSync(file) && create) {
    writeFileSync(file, readFileSync(path.join(root, ".env.example"), "utf8"), { mode: 0o600, flag: "wx" });
    console.log("Created ignored .env from .env.example.");
  }
  const values = existsSync(file) ? parseEnv(readFileSync(file, "utf8")) : {};
  return { ...process.env, ...values, NEXT_TELEMETRY_DISABLED: "1" };
}
