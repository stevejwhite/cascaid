import { createServer } from "node:net";
import { randomBytes, randomUUID } from "node:crypto";
import { chmod, mkdir, readFile, writeFile, rename, rm, lstat } from "node:fs/promises";
import path from "node:path";
import { alive, delay, freePorts, service, stopChildren, waitFor } from "./processes.mjs";
import { preflight } from "./preflight.mjs";
import { smoke } from "./smoke.mjs";

const healthy = async (url) => fetch(url, { signal: AbortSignal.timeout(10000) })
  .then((r) => r.ok).catch(() => false);

// The web proxy forwards only /backend/api/*, so readiness is the API's loopback probe
// plus the web server answering its home page.
export const serving = async (c) => await healthy(`http://127.0.0.1:${c.apiPort}/ready`) &&
  await healthy(`http://127.0.0.1:${c.webPort}/`);

export async function supervise(c) {
  process.umask(0o077);
  await preflight(c);
  const lock = path.join(c.stateDir, "supervisor.lock");
  await mkdir(lock, { mode: 0o700 }).catch(() => {
    throw new Error("Production lock exists. Use production:status; see the runbook for interrupted-start recovery.");
  });
  let stopping = false, children = [], attempts = 0, cycle, ownsSocket = false, ownsState = false;
  const state = { id: randomUUID(), pid: process.pid, release: c.release,
    started_at: new Date().toISOString(), status: "starting", restarts: 0, profile: c.profile };
  // Online only: a fresh secret per supervisor, given to the API processes alone (not the
  // web or model servers) and kept in the private state directory for production:smoke.
  let apiEnv = c.env, ownsToken = false;
  const save = async () => {
    await writeFile(c.stateFile + ".tmp", JSON.stringify(state, null, 2) + "\n", { mode: 0o600 });
    await rename(c.stateFile + ".tmp", c.stateFile);
  };
  const stop = () => { stopping = true; state.status = "stopping"; cycle?.abort(); };
  const socket = createServer({ allowHalfOpen: true }, (client) => {
    let input = "";
    client.setTimeout(3000, () => client.destroy());
    client.on("error", () => {});
    client.on("data", (chunk) => {
      input += chunk;
      if (input.length > 2048) { client.destroy(); return; }
      if (!input.includes("\n")) return;
      try {
        const message = JSON.parse(input);
        if (message.action === "stop" && message.id === state.id) stop();
        else if (message.action !== "status") { client.end('{"error":"Rejected"}\n'); return; }
        client.end(JSON.stringify(state) + "\n");
      } catch { client.end('{"error":"Invalid request"}\n'); }
    });
  });
  process.on("SIGINT", stop); process.on("SIGTERM", stop);
  const spawn = (name, program, args, env = c.env) => {
    const thisCycle = cycle;
    const child = service(program, args, { cwd: c.release, env }, path.join(c.logDir, `${name}.log`));
    children.push(child);
    // Abort pending warm-up immediately if any required service disappears.
    child.once("exit", () => thisCycle.abort());
    child.once("error", () => thisCycle.abort());
    return child;
  };
  try {
    if (await lstat(c.socket).catch(() => null)) throw new Error("Control socket already exists; inspect it before recovering the deployment");
    await save();
    ownsState = true;
    await new Promise((resolve, reject) => {
      socket.once("error", reject); socket.listen(c.socket, resolve);
    });
    ownsSocket = true;
    await chmod(c.socket, 0o600);
    if (c.online) {
      c.internalToken = randomBytes(32).toString("hex");
      apiEnv = { ...c.env, CASCAID_INTERNAL_TOKEN: c.internalToken };
      await writeFile(c.tokenFile, c.internalToken + "\n", { mode: 0o600, flag: "wx" }).catch(() => {
        throw new Error("Internal token file already exists; inspect it before recovering the deployment");
      });
      ownsToken = true;
    }
    while (!stopping) {
      cycle = new AbortController();
      c.abortSignal = cycle.signal;
      try {
        await freePorts(c.ports);
        state.status = "starting"; state.restarts = attempts; await save();
        for (const name of ["models", "speech", "student", "tts"]) {
          const file = name === "models" ? "runtime-state.json" : `${name}-state.json`;
          await rm(path.join(c.stateDir, file), { force: true });
          const child = spawn(name, process.execPath, [path.join(c.release, `scripts/${name}/start.mjs`)]);
          await waitFor(async () => {
            const record = await readFile(path.join(c.stateDir, file), "utf8").then(JSON.parse).catch(() => null);
            return record?.pid === child.pid;
          }, children, () => stopping || cycle.signal.aborted);
        }
        state.status = "warming-classifiers"; await save();
        // Cold classifier embeddings can exceed an interview request's timeout.
        // Build that cache separately before the API starts accepting requests.
        const warm = service(path.join(c.release, "services/api/.venv/bin/python"),
          ["-m", "psychiatry_api.production_warmup"], { cwd: c.release, env: apiEnv },
          path.join(c.logDir, "classifiers.log"));
        children.push(warm);
        const deadline = Date.now() + 15 * 60 * 1000;
        while (alive(warm)) {
          if (stopping || cycle.signal.aborted || Date.now() > deadline) throw new Error("Classifier warm-up interrupted or timed out");
          await delay(500);
        }
        children = children.filter((child) => child !== warm);
        if (warm.exitCode !== 0 || warm.spawnError) throw new Error("Classifier warm-up failed; inspect classifiers.log");
        spawn("api", path.join(c.release, "services/api/.venv/bin/uvicorn"), [
          "psychiatry_api.main:app", "--host", "127.0.0.1", "--port", String(c.apiPort),
          "--workers", "1", "--no-access-log",
        ], apiEnv);
        await waitFor(() => healthy(`http://127.0.0.1:${c.apiPort}/ready`), children, () => stopping || cycle.signal.aborted);
        state.status = "warming"; await save();
        await smoke(c);
        if (stopping || cycle.signal.aborted) throw new Error("Warm-up interrupted");
        spawn("web", process.execPath, [path.join(c.release, "node_modules/next/dist/bin/next"),
          "start", "apps/web", "--hostname", "127.0.0.1", "--port", String(c.webPort)]);
        await waitFor(() => serving(c), children, () => stopping || cycle.signal.aborted);
        state.status = "ready"; await save();
        console.log(c.online
          ? `Production ready: http://127.0.0.1:${c.webPort}, published only through the Cloudflare tunnel as ${c.publicOrigin}`
          : `Production ready: http://127.0.0.1:${c.webPort} (local only)`);
        let missedChecks = 0;
        while (!stopping) {
          if (children.some((child) => !alive(child))) throw new Error("Required service exited");
          // One slow health response under inference load must not kill an interview.
          missedChecks = await serving(c) ? 0 : missedChecks + 1;
          if (missedChecks >= 3) throw new Error("Required service failed three consecutive readiness checks");
          await delay(3000);
        }
      } catch (error) {
        if (!stopping) console.error(`Production unavailable: ${error.message}`);
        state.status = stopping ? "stopping" : "unavailable"; await save();
      } finally {
        // Close the public-facing listener first, then all owned runtime groups.
        cycle.abort();
        await stopChildren(children); children = [];
      }
      if (stopping) break;
      if (attempts >= 2) throw new Error("Restart limit reached (two retries). Fix the cause and start manually.");
      attempts++; await delay(2000);
    }
  } finally {
    stopping = true; cycle?.abort();
    await stopChildren(children);
    if (ownsSocket) {
      socket.close();
      await rm(c.socket, { force: true });
    }
    if (ownsState) await rm(c.stateFile, { force: true });
    if (ownsToken) await rm(c.tokenFile, { force: true });
    delete c.internalToken;
    await rm(lock, { recursive: true, force: true });
    process.off("SIGINT", stop); process.off("SIGTERM", stop);
  }
}
