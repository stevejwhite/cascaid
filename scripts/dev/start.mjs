import { spawn } from "node:child_process";
import { existsSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { createServer } from "node:net";
import path from "node:path";
import { root, environment } from "./config.mjs";

const env = environment({ create: true });
const children = new Set();
const state = path.join(root, "artifacts/dev/supervisor.json");
let stopping = false;
let ownsState = false;

function run(command, args) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd: root, env, stdio: "inherit" });
    children.add(child);
    child.once("error", reject);
    child.once("exit", (code) => {
      children.delete(child);
      code === 0 ? resolve() : reject(new Error(`${command} exited with status ${code}`));
    });
  });
}
function service(command, args) {
  const child = spawn(command, args, { cwd: root, env, stdio: "inherit", detached: true });
  children.add(child);
  child.once("error", (error) => { console.error(error.message); shutdown(1); });
  child.once("exit", (code) => { children.delete(child); if (!stopping) shutdown(code || 1); });
}
function shutdown(code = 0) {
  if (stopping) return;
  stopping = true;
  process.exitCode = code;
  for (const child of children) {
    try { process.kill(-child.pid, "SIGTERM"); } catch { child.kill("SIGTERM"); }
  }
  if (ownsState) rmSync(state, { force: true });
  console.log("Application stopped.");
  setTimeout(() => process.exit(code), 500).unref();
}
process.on("SIGINT", () => shutdown());
process.on("SIGTERM", () => shutdown());

async function assertFree(port) {
  await new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", () => reject(new Error(`Port ${port} is in use. Stop this app or change its .env ports.`)));
    server.listen(Number(port), "127.0.0.1", () => server.close(resolve));
  });
}

try {
  await assertFree(env.API_PORT || 8105);
  await assertFree(env.WEB_PORT || 3105);
  if (!existsSync(path.join(root, "node_modules/next"))) await run("npm", ["ci"]);
  await run("uv", ["sync", "--project", "services/api", "--locked"]);
  // The hands-free voice-activity model and runtime, served by the web app (public/vad).
  await run(process.execPath, ["apps/web/scripts/vad-assets.mjs"]);
  mkdirSync(path.dirname(state), { recursive: true });
  writeFileSync(state, JSON.stringify({ pid: process.pid, root }));
  ownsState = true;
  service("uv", ["run", "--project", "services/api", "--locked", "uvicorn", "psychiatry_api.main:app", "--host", "127.0.0.1", "--port", env.API_PORT || "8105",
    // Restart the API when its code changes, as the web app already does, so a running
    // API never lags behind the case schema or prompts it reads.
    "--reload", "--reload-dir", "services/api/src"]);
  service(process.execPath, ["node_modules/next/dist/bin/next", "dev", "apps/web", "--hostname", "127.0.0.1", "--port", env.WEB_PORT || "3105"]);
  console.log(`Web: http://127.0.0.1:${env.WEB_PORT || 3105} | API: http://127.0.0.1:${env.API_PORT || 8105}/docs`);
} catch (error) {
  console.error(error.message);
  shutdown(1);
}
