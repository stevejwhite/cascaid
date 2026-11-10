import test from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, writeFile, mkdir, rm, readFile, chmod, cp, symlink } from "node:fs/promises";
import { realpathSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { createServer } from "node:net";
import { spawn } from "node:child_process";
import { once } from "node:events";
import { loadConfig, sourceRoot } from "../config.mjs";
import { freePorts, service, stopChildren, alive, waitFor, control, runRelease } from "../processes.mjs";
import { configDigest, hashFile, verifyRelease } from "../release.mjs";
import { verifyAssets, directories } from "../preflight.mjs";
import { request } from "../smoke.mjs";

async function fixture(t) {
  const directory = await mkdtemp(path.join(realpathSync(tmpdir()), "cp-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  const file = path.join(directory, "production.env");
  await writeFile(file, `DEPLOYMENT_PROFILE=production-local\nRELEASE_ROOT=${directory}/release\nPERSISTENT_ROOT=${directory}/var\nNATIVE_MODEL_HOME=${directory}/models\n`, { mode: 0o600 });
  return { directory, file, c: loadConfig(file) };
}

test("production environment isolates development settings and persistent paths", async (t) => {
  const original = process.env.MODEL_BACKEND;
  process.env.MODEL_BACKEND = "fake";
  t.after(() => { if (original === undefined) delete process.env.MODEL_BACKEND; else process.env.MODEL_BACKEND = original; });
  const { c } = await fixture(t);
  assert.equal(c.env.MODEL_BACKEND, "local");
  assert.equal(c.env.CASCAID_PRODUCTION_ACTIVE, "1");
  assert.equal(c.env.RECORDINGS_ENABLED, "false");
  assert.ok(c.env.SESSIONS_PATH.startsWith(c.persistent));
  assert.ok(!c.env.SESSIONS_PATH.startsWith(c.release));
  assert.equal(c.env.API_BASE_URL, "http://127.0.0.1:8105");
});

test("rejects insecure files, unknown overrides, online profiles and colliding ports", async (t) => {
  const { file } = await fixture(t);
  const contents = await readFile(file, "utf8");
  await chmod(file, 0o644);
  assert.throws(() => loadConfig(file), /mode 600/);
  await chmod(file, 0o600);
  for (const [value, pattern] of [
    [contents + "MODEL_BACKEND=fake\n", /Unsupported/],
    [contents.replace("production-local", "online"), /production-local or production-online/],
    [contents + "PUBLIC_ORIGIN=https://cascaid.example.org\n", /only accepted by the production-online/],
    [contents + "WEB_PORT=8180\n", /conflict/],
    [contents.replace(/PERSISTENT_ROOT=.*/, "PERSISTENT_ROOT=relative"), /absolute/],
  ]) {
    await writeFile(file, value);
    assert.throws(() => loadConfig(file), pattern);
  }
});

test("occupied port fails preflight without affecting its owner", async (t) => {
  const server = createServer();
  server.listen(0, "127.0.0.1"); await once(server, "listening");
  t.after(() => server.close());
  await assert.rejects(freePorts([server.address().port]), /will not kill or reuse/);
  assert.ok(server.listening);
});

test("shutdown terminates owned descendants and leaves unrelated processes alive", async (t) => {
  const { directory } = await fixture(t);
  const unrelated = spawn(process.execPath, ["-e", "setInterval(()=>{},1000)"], { stdio: "ignore" });
  t.after(() => unrelated.kill());
  const pidFile = path.join(directory, "grandchild");
  const code = `const {spawn}=require('child_process'); const fs=require('fs'); const c=spawn(process.execPath,['-e','setInterval(()=>{},1000)']); fs.writeFileSync(${JSON.stringify(pidFile)},String(c.pid)); setInterval(()=>{},1000);`;
  const child = service(process.execPath, ["-e", code], {}, path.join(directory, "child.log"));
  t.after(() => stopChildren([child]));
  await waitFor(() => readFile(pidFile).then(() => true).catch(() => false), [child], () => false, 5000);
  const descendant = Number(await readFile(pidFile, "utf8"));
  await stopChildren([child]);
  assert.equal(alive(child), false);
  assert.throws(() => process.kill(descendant, 0));
  assert.doesNotThrow(() => process.kill(unrelated.pid, 0));
});

test("readiness stops waiting when its service exits or startup is cancelled", async () => {
  const exited = { exitCode: 1, signalCode: null };
  await assert.rejects(waitFor(async () => true, [exited], () => false), /exited/);
  await assert.rejects(waitFor(async () => true, [], () => true), /cancelled/);
});

test("missing model assets fail explicitly without attempting acquisition", async (t) => {
  const { c } = await fixture(t);
  await cp(path.join(sourceRoot, "config"), path.join(c.release, "config"), { recursive: true });
  await assert.rejects(verifyAssets(c), /Missing or unverified installed asset/);
});

test("prepared release rejects configuration drift, changed files and extra inputs", async (t) => {
  const { c } = await fixture(t);
  await mkdir(c.release);
  const name = "app.txt";
  await writeFile(path.join(c.release, name), "original");
  for (const file of ["apps/web/.next/BUILD_ID", "node_modules/next/dist/bin/next",
    "services/api/.venv/bin/uvicorn", "tools/finetune/.venv/bin/mlx_lm.server"]) {
    await mkdir(path.dirname(path.join(c.release, file)), { recursive: true });
    await writeFile(path.join(c.release, file), "prepared");
  }
  await writeFile(path.join(c.release, "production-release.json"), JSON.stringify({
    config: configDigest(c), node: process.version, build_id: "prepared", hashes: { [name]: await hashFile(path.join(c.release, name)) },
  }));
  await verifyRelease(c);
  await writeFile(path.join(c.release, "apps/web/.env.local"), "MODEL_BACKEND=fake");
  await assert.rejects(verifyRelease(c), /must not contain .env/);
  await rm(path.join(c.release, "apps/web/.env.local"));
  await assert.rejects(verifyRelease({ ...c, apiPort: 8106 }), /configuration/);
  await writeFile(path.join(c.release, name), "changed");
  await assert.rejects(verifyRelease(c), /changed/);
  await writeFile(path.join(c.release, "extra.txt"), "new");
  await assert.rejects(verifyRelease(c), /inventory/);
});

test("missing control socket never falls back to signalling a recorded PID", async (t) => {
  const { c } = await fixture(t);
  await assert.rejects(control(c.socket, { action: "stop", id: "wrong" }), /ENOENT/);
});

test("production refuses symlinked state directories", async (t) => {
  const { c, directory } = await fixture(t);
  await mkdir(c.persistent, { mode: 0o700 });
  const other = path.join(directory, "other-state");
  await mkdir(other, { mode: 0o700 });
  await symlink(other, c.stateDir);
  await assert.rejects(directories(c), /must not use symlinks/);
});

test("release dispatcher reports failed starts and removes signal handlers", async () => {
  const before = process.listenerCount("SIGTERM");
  await runRelease(process.execPath, ["-e", "process.exit(0)"], {});
  await assert.rejects(runRelease(process.execPath, ["-e", "process.exit(2)"], {}), /exited \(2\)/);
  assert.equal(process.listenerCount("SIGTERM"), before);
});

const ONLINE = ["DEPLOYMENT_PROFILE=production-online", "ACCESS_TEAM_DOMAIN=cascaid-test.cloudflareaccess.com",
  `ACCESS_AUDIENCE=${"a".repeat(64)}`, "ACCESS_ALLOWED_EMAILS=owner@example.org",
  "PUBLIC_ORIGIN=https://cascaid.example.org"];

test("online profile requires complete Access settings and keeps every listener on loopback", async (t) => {
  const { file } = await fixture(t);
  const base = (await readFile(file, "utf8")).replace(/DEPLOYMENT_PROFILE=.*\n/, "");
  await writeFile(file, base + ONLINE.join("\n") + "\n");
  const c = loadConfig(file);
  assert.equal(c.online, true);
  assert.equal(c.env.DEPLOYMENT_PROFILE, "production-online");
  assert.equal(c.env.PUBLIC_ORIGIN, "https://cascaid.example.org");
  assert.equal(c.env.API_BASE_URL, `http://127.0.0.1:${c.apiPort}`);
  assert.equal(c.env.CASCAID_INTERNAL_TOKEN, undefined, "the secret is created per start, not configured");
  assert.ok(c.tokenFile.startsWith(c.stateDir));
  for (const [key, value] of [["ACCESS_TEAM_DOMAIN", "evil.example.com"], ["ACCESS_AUDIENCE", "short"],
    ["ACCESS_ALLOWED_EMAILS", "nobody"], ["PUBLIC_ORIGIN", "http://cascaid.example.org"],
    ["PUBLIC_ORIGIN", "https://cascaid.example.org/"], ["PUBLIC_ORIGIN", "https://cascaid.example.org:8443"]]) {
    const lines = ONLINE.map((line) => line.startsWith(key + "=") ? `${key}=${value}` : line);
    await writeFile(file, base + lines.join("\n") + "\n");
    assert.throws(() => loadConfig(file), new RegExp(key), `${key}=${value}`);
  }
  for (const missing of ONLINE.slice(1)) {
    await writeFile(file, base + ONLINE.filter((line) => line !== missing).join("\n") + "\n");
    assert.throws(() => loadConfig(file), new RegExp(missing.split("=")[0]));
  }
});

test("smoke requests carry the internal secret only when one is given", async (t) => {
  const { createServer: http } = await import("node:http");
  const seen = [];
  const server = http((req, res) => { seen.push(req.headers["x-cascaid-internal"]); res.end("{}"); });
  server.listen(0, "127.0.0.1"); await once(server, "listening");
  t.after(() => server.close());
  const base = `http://127.0.0.1:${server.address().port}`;
  await request(base, "/api/cases", undefined, undefined, "f".repeat(64));
  await request(base, "/api/sessions", { case_id: "x" });
  assert.deepEqual(seen, ["f".repeat(64), undefined]);
});

test("on-demand jobs start when loaded, never at login, and the tunnel targets only the web port", async (t) => {
  const { directory, file } = await fixture(t);
  const base = (await readFile(file, "utf8")).replace(/DEPLOYMENT_PROFILE=.*\n/, "");
  await writeFile(file, base + ONLINE.join("\n") + "\n");
  const c = loadConfig(file);
  const { productionPlist, tunnelPlist, checkTunnel, tunnelSettings } = await import("../online.mjs");
  const production = productionPlist(c);
  assert.match(production, /<key>Label<\/key><string>uk\.cascaid\.production<\/string>/);
  assert.match(production, /<key>KeepAlive<\/key><false\/>/);
  assert.ok(production.includes(c.file));
  // A fake cloudflared that answers ingress queries from the rules it is given.
  const fake = path.join(directory, "cloudflared");
  const rules = path.join(directory, "rules");
  await writeFile(fake, `#!/bin/sh\ncase "$*" in *validate*) exit 0;; esac\nfor last; do :; done\ncase "$last" in https://cascaid.example.org) sed -n 1p ${rules};; *) sed -n 2p ${rules};; esac\n`, { mode: 0o755 });
  const tunnelConfig = path.join(directory, "config.yml");
  await writeFile(tunnelConfig, "tunnel: x\n");
  const settings = tunnelSettings({ CLOUDFLARED: fake, CASCAID_TUNNEL_CONFIG: tunnelConfig });
  for (const [first, second, ok] of [
    ["service: http://127.0.0.1:3105", "service: http_status:404", true],
    ["service: http://127.0.0.1:8105", "service: http_status:404", false],
    ["service: http://127.0.0.1:3105", "service: http://127.0.0.1:3105", false],
  ]) {
    await writeFile(rules, `${first}\n${second}\n`);
    if (ok) await checkTunnel(c, settings);
    else await assert.rejects(checkTunnel(c, settings));
  }
  const tunnel = tunnelPlist(c, settings);
  assert.match(tunnel, /<key>Label<\/key><string>uk\.cascaid\.tunnel<\/string>/);
  assert.ok(tunnel.includes("--no-autoupdate") && tunnel.includes(tunnelConfig));
  assert.match(tunnel, /<key>SuccessfulExit<\/key><false\/>/);
  assert.throws(() => tunnelSettings({ CLOUDFLARED: path.join(directory, "missing"), CASCAID_TUNNEL_CONFIG: path.join(directory, "none.yml") }), /not found/);
});
