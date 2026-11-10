import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { root } from "./dev/config.mjs";

const check = process.argv.includes("--check");
const directory = mkdtempSync(path.join(os.tmpdir(), "psychiatry-contracts-"));
try {
  const schema = execFileSync("uv", ["run", "--project", "services/api", "--locked", "python", "-m", "psychiatry_api.openapi"], { cwd: root, encoding: "utf8" });
  const schemaFile = path.join(directory, "openapi.json");
  const typesFile = path.join(directory, "api.generated.ts");
  writeFileSync(schemaFile, schema);
  execFileSync(process.execPath, [path.join(root, "node_modules/openapi-typescript/bin/cli.js"), schemaFile, "-o", typesFile], { cwd: root, stdio: "pipe" });
  for (const [name, content] of [["openapi.json", schema], ["api.generated.ts", readFileSync(typesFile, "utf8")]]) {
    const target = path.join(root, "apps/web/lib", name);
    if (check) {
      if (readFileSync(target, "utf8") !== content) throw new Error(`${name} is stale. Run npm run contracts:generate.`);
    } else writeFileSync(target, content);
  }
  console.log(check ? "API contracts match generated TypeScript." : "API contracts generated.");
} finally { rmSync(directory, { recursive: true, force: true }); }
