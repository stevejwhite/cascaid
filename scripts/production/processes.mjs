import { spawn } from "node:child_process";
import { openSync, closeSync, existsSync, renameSync, statSync } from "node:fs";
import { createServer, createConnection } from "node:net";

export const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export async function freePorts(ports) {
  for (const port of ports) await new Promise((resolve, reject) => {
    const server = createServer();
    server.once("error", () => reject(new Error(`Port ${port} is occupied. Stop the owning development/model service first; production will not kill or reuse it.`)));
    server.listen(port, "127.0.0.1", () => server.close(resolve));
  });
}

export function command(program, args, options) {
  return new Promise((resolve, reject) => {
    const child = spawn(program, args, { stdio: "inherit", ...options });
    child.once("error", reject);
    child.once("exit", (code) => code === 0 ? resolve() : reject(new Error(`${program} failed (${code})`)));
  });
}

export async function runRelease(program, args, options) {
  const child = spawn(program, args, { stdio: "inherit", ...options });
  const interrupt = () => child.kill("SIGINT");
  const terminate = () => child.kill("SIGTERM");
  process.on("SIGINT", interrupt); process.on("SIGTERM", terminate);
  try {
    await new Promise((resolve, reject) => {
      child.once("error", reject);
      child.once("exit", (code) => code === 0 ? resolve() : reject(new Error(`Production supervisor exited (${code})`)));
    });
  } finally {
    process.off("SIGINT", interrupt); process.off("SIGTERM", terminate);
  }
}

export function service(program, args, options, logFile) {
  // Bound each restart's log retention; native launchers also truncate their own logs.
  if (existsSync(logFile) && statSync(logFile).size > 0) renameSync(logFile, logFile + ".previous");
  const fd = openSync(logFile, "w", 0o600);
  const child = spawn(program, args, { ...options, detached: true, stdio: ["ignore", fd, fd] });
  closeSync(fd);
  child.spawnError = null;
  child.once("error", (error) => { child.spawnError = error; });
  return child;
}

export const alive = (child) => child && !child.spawnError && child.exitCode === null && child.signalCode === null;

export async function stopChildren(children) {
  // Only process groups created by this supervisor: never inspect ports to kill owners.
  for (const child of [...children].reverse()) {
    if (!child.pid) continue;
    try { process.kill(-child.pid, "SIGTERM"); } catch { /* already exited */ }
  }
  await delay(1000);
  for (const child of children) {
    if (!child.pid) continue;
    try { process.kill(-child.pid, "SIGKILL"); } catch { /* group is gone */ }
  }
}

export async function waitFor(check, children, aborted, timeoutMs = 240000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (aborted()) throw new Error("Startup cancelled");
    if (children.some((child) => !alive(child))) throw new Error("A required service exited; inspect production logs");
    if (await check()) return;
    await delay(500);
  }
  throw new Error("Service readiness timed out; inspect production logs");
}

export async function control(socket, message) {
  return new Promise((resolve, reject) => {
    const client = createConnection(socket);
    let buffer = "";
    client.setTimeout(3000, () => client.destroy(new Error("Control request timed out")));
    client.on("error", reject);
    client.on("connect", () => client.end(JSON.stringify(message) + "\n"));
    client.on("data", (chunk) => { buffer += chunk; });
    client.on("end", () => {
      try { resolve(JSON.parse(buffer)); } catch { reject(new Error("Invalid supervisor reply")); }
    });
  });
}
