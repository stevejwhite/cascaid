// On-demand online pilot: start CascAid and its Cloudflare tunnel when required, stop
// both afterwards. Both run as launchd jobs loaded for this login session only. Nothing
// is placed in ~/Library/LaunchAgents, so neither starts at login or after a reboot.
import { execFile } from "node:child_process";
import { existsSync } from "node:fs";
import { readFile, writeFile } from "node:fs/promises";
import { homedir } from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { control, delay } from "./processes.mjs";

const run = promisify(execFile);
export const LABELS = { production: "uk.cascaid.production", tunnel: "uk.cascaid.tunnel" };
const domain = () => `gui/${process.getuid()}`;
const xml = (text) => String(text).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;");

export function plist({ label, args, cwd, env, out, err, keepAlive = false }) {
  return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>${xml(label)}</string>
<key>ProgramArguments</key><array>${args.map((v) => `<string>${xml(v)}</string>`).join("")}</array>
<key>WorkingDirectory</key><string>${xml(cwd)}</string>
<key>EnvironmentVariables</key><dict>
${Object.entries(env).map(([k, v]) => `<key>${xml(k)}</key><string>${xml(v)}</string>`).join("\n")}
</dict>
<key>RunAtLoad</key><true/>
<key>KeepAlive</key>${keepAlive ? "<dict><key>SuccessfulExit</key><false/></dict>" : "<false/>"}
<key>StandardOutPath</key><string>${xml(out)}</string>
<key>StandardErrorPath</key><string>${xml(err)}</string>
</dict></plist>
`;
}

export function productionPlist(c) {
  return plist({
    label: LABELS.production,
    args: [process.execPath, path.join(c.release, "scripts/production/cli.mjs"), "start"],
    cwd: c.release,
    env: { CASCAID_PRODUCTION_CONFIG: c.file, PATH: process.env.PATH || "/usr/bin:/bin" },
    out: path.join(c.logDir, "launchd.log"), err: path.join(c.logDir, "launchd-error.log"),
  });
}

/** The tunnel binary and configuration: overridable, with this Mac's install as default. */
export function tunnelSettings(env = process.env) {
  const candidates = [env.CLOUDFLARED, path.join(homedir(), ".local/bin/cloudflared"),
    "/opt/homebrew/bin/cloudflared", "/usr/local/bin/cloudflared"].filter(Boolean);
  const binary = candidates.find((file) => existsSync(file));
  if (!binary) throw new Error("cloudflared not found; set CLOUDFLARED to its path");
  const config = env.CASCAID_TUNNEL_CONFIG || path.join(homedir(), ".cloudflared/config.yml");
  if (!existsSync(config)) throw new Error(`Tunnel configuration not found: ${config}`);
  return { binary, config };
}

/** Refuse a tunnel that would publish anything but this deployment's web port. */
export async function checkTunnel(c, t) {
  const rule = async (url) => {
    const { stdout, stderr } = await run(t.binary, ["tunnel", "--config", t.config, "ingress", "rule", url]);
    return stdout + stderr;
  };
  await run(t.binary, ["tunnel", "--config", t.config, "ingress", "validate"]);
  const host = new URL(c.publicOrigin).hostname;
  if (!(await rule(`https://${host}`)).includes(`service: http://127.0.0.1:${c.webPort}`)) {
    throw new Error(`Tunnel rule for ${host} must be http://127.0.0.1:${c.webPort} only`);
  }
  if (!(await rule("https://unmatched.invalid")).includes("http_status:404")) {
    throw new Error("Tunnel configuration needs a final http_status:404 catch-all rule");
  }
}

export function tunnelPlist(c, t) {
  return plist({
    label: LABELS.tunnel,
    args: [t.binary, "tunnel", "--no-autoupdate", "--config", t.config, "run"],
    cwd: c.persistent,
    env: { HOME: homedir(), PATH: "/usr/bin:/bin" },
    out: path.join(c.logDir, "tunnel.log"), err: path.join(c.logDir, "tunnel.log"),
    // Reconnect after a crash; bootout (online:stop) ends it for good.
    keepAlive: true,
  });
}

export const loaded = (label) => run("launchctl", ["print", `${domain()}/${label}`]).then(() => true, () => false);

export async function load(label, file, contents) {
  if (await loaded(label)) throw new Error(`${label} is already loaded; use online:status or online:stop`);
  await writeFile(file, contents, { mode: 0o600 });
  await run("launchctl", ["bootstrap", domain(), file]);
}

export async function unload(label) {
  if (!(await loaded(label))) return false;
  await run("launchctl", ["bootout", `${domain()}/${label}`]);
  for (let i = 0; i < 20 && await loaded(label); i++) await delay(500);
  return true;
}

export const supervisorStatus = (c) => control(c.socket, { action: "status" }).catch(() => null);

/** Wait for the supervisor to report ready, printing each state change. */
export async function waitReady(c, timeoutMs = 25 * 60 * 1000, log = console.log) {
  const deadline = Date.now() + timeoutMs;
  let last;
  while (Date.now() < deadline) {
    const record = await supervisorStatus(c);
    if (record?.status !== last && record?.status) log(`CascAid: ${(last = record.status)}`);
    if (record?.status === "ready") return;
    if (!record && !(await loaded(LABELS.production))) throw new Error("CascAid exited during startup");
    if (record?.status === "unavailable" && record.restarts >= 2) throw new Error("CascAid could not start");
    await delay(2000);
  }
  throw new Error("CascAid did not become ready in time");
}

export async function waitTunnel(logFile, since, timeoutMs = 60000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const text = await readFile(logFile, "utf8").catch(() => "");
    if (text.slice(since).includes("Registered tunnel connection")) return;
    if (!(await loaded(LABELS.tunnel))) throw new Error("The tunnel exited; inspect tunnel.log");
    await delay(1000);
  }
  throw new Error("The tunnel did not connect in time; inspect tunnel.log");
}
