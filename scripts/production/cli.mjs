import { readFile, stat, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import path from "node:path";
import { loadConfig, sourceRoot } from "./config.mjs";
import { prepare } from "./release.mjs";
import { preflight, directories } from "./preflight.mjs";
import { control, delay, runRelease } from "./processes.mjs";
import { serving, supervise } from "./supervisor.mjs";
import { smoke } from "./smoke.mjs";
import { LABELS, checkTunnel, load, loaded, productionPlist, supervisorStatus, tunnelPlist,
  tunnelSettings, unload, waitReady, waitTunnel } from "./online.mjs";

async function stopSupervisor(c) {
  const record = await readFile(c.stateFile, "utf8").then(JSON.parse).catch(() => null);
  if (!record) { console.log("No recorded production supervisor. No processes were signalled."); return; }
  if (record.release !== c.release) throw new Error("Recorded release does not match; refusing to stop it");
  const result = await control(c.socket, { action: "stop", id: record.id });
  if (result.status !== "stopping") throw new Error("Supervisor rejected the stop request");
  for (let i = 0; i < 60; i++) {
    await delay(500);
    if (!await control(c.socket, { action: "status" }).catch(() => null)) {
      console.log("Production stopped. Unrelated processes were not signalled.");
      return;
    }
  }
  throw new Error("Stop is still in progress; inspect production:status");
}

try {
  process.umask(0o077);
  const action = process.argv[2];
  // The online:* commands default to this Mac's online configuration.
  if (action?.startsWith("online-") && !process.env.CASCAID_PRODUCTION_CONFIG) {
    process.env.CASCAID_PRODUCTION_CONFIG = path.join(homedir(), "CascAid/production-online.env");
  }
  const c = loadConfig();
  if (action === "prepare") {
    console.log("Preparing an isolated release using cached dependencies; no models will be downloaded.");
    await prepare(c);
    console.log(`Prepared ${c.release}. Stop development/model services before production:preflight.`);
  } else if (action === "preflight") {
    console.log(JSON.stringify(await preflight(c), null, 2));
  } else if (action === "start") {
    console.log("Checking production ports, prepared release and installed model checksums…");
    if (sourceRoot !== c.release) {
      // Pin the supervisor as well as the servers to the prepared release. Editing
      // the development checkout must not alter a running deployment's behaviour.
      await runRelease(process.execPath, [path.join(c.release, "scripts/production/cli.mjs"), "start"],
        { cwd: c.release, env: c.env });
    } else await supervise(c);
  } else if (action === "status") {
    const record = await control(c.socket, { action: "status" }).catch(() => null);
    if (!record) {
      console.log(JSON.stringify({ status: "stopped-or-unreachable", release: c.release }));
      process.exitCode = 1;
    } else {
      const ready = await serving(c);
      console.log(JSON.stringify({ ...record, checks: ready ? "ready" : "not_ready" }, null, 2));
      if (record.status !== "ready" || !ready) process.exitCode = 1;
    }
  } else if (action === "stop") {
    await stopSupervisor(c);
  } else if (action === "smoke") {
    const state = await control(c.socket, { action: "status" });
    if (state.status !== "ready") throw new Error("Production must be ready before the smoke test");
    // Locally the smoke test goes through the web proxy. Online, the API admits it only with
    // the supervisor's secret, which the proxy refuses to forward, so it uses the API port.
    const result = c.online
      ? await smoke(c, `http://127.0.0.1:${c.apiPort}`, (await readFile(c.tokenFile, "utf8")).trim())
      : await smoke(c, `http://127.0.0.1:${c.webPort}/backend`);
    console.log(JSON.stringify(result));
  } else if (action === "service-file") {
    await directories(c);
    const file = path.join(c.persistent, "uk.cascaid.production.plist");
    await writeFile(file, productionPlist(c), { mode: 0o600 });
    console.log(`Generated ${file}. Not installed; follow the runbook.`);
  } else if (action === "online-start") {
    if (!c.online) throw new Error("online:start needs a production-online configuration");
    const t = tunnelSettings();
    // Check everything that can fail quickly before loading any model.
    await checkTunnel(c, t);
    if (await loaded(LABELS.tunnel)) throw new Error("The tunnel is already running; use online:status or online:stop");
    if (!(await supervisorStatus(c))) {
      console.log("Checking ports, release and model checksums…");
      await preflight(c);
      await load(LABELS.production, path.join(c.persistent, `${LABELS.production}.plist`), productionPlist(c));
      console.log("Starting CascAid in the background (several minutes on a cold start)…");
    }
    try {
      await waitReady(c);
    } catch (error) {
      await unload(LABELS.production);
      throw new Error(`${error.message}. Logs: ${c.logDir}`);
    }
    const tunnelLog = path.join(c.logDir, "tunnel.log");
    const since = await stat(tunnelLog).then((s) => s.size, () => 0);
    await load(LABELS.tunnel, path.join(c.persistent, `${LABELS.tunnel}.plist`), tunnelPlist(c, t));
    try {
      await waitTunnel(tunnelLog, since);
    } catch (error) {
      await unload(LABELS.tunnel);
      throw error;
    }
    console.log(`Online: ${c.publicOrigin} (Cloudflare sign-in required). Stop with npm run online:stop.`);
  } else if (action === "online-stop") {
    // Close external access first, then the local services.
    console.log(await unload(LABELS.tunnel) ? "Tunnel stopped; the hostname is no longer served." : "Tunnel was not running.");
    if (await supervisorStatus(c)) await stopSupervisor(c);
    else console.log("CascAid was not running.");
    await unload(LABELS.production);
  } else if (action === "online-status") {
    const record = await supervisorStatus(c);
    const tunnel = await loaded(LABELS.tunnel);
    const ready = record?.status === "ready" && await serving(c);
    console.log(JSON.stringify({ cascaid: record?.status ?? "stopped", checks: ready ? "ready" : "not_ready",
      tunnel: tunnel ? "running" : "stopped", url: c.publicOrigin }, null, 2));
    if (!ready || !tunnel) process.exitCode = 1;
  } else throw new Error("Use prepare, preflight, start, stop, status, smoke, service-file, online-start, online-stop or online-status");
} catch (error) { console.error(error.message); process.exitCode = 1; }
