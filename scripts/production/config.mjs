import { readFileSync, statSync, realpathSync, existsSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { parseEnv } from "node:util";

export const sourceRoot = fileURLToPath(new URL("../../", import.meta.url)).replace(/\/$/, "");
export const within = (parent, child) => child === parent || child.startsWith(parent + path.sep);

function absolute(value, key) {
  if (!value || !path.isAbsolute(value)) throw new Error(`${key} must be an absolute path`);
  const resolved = path.resolve(value);
  let existing = resolved;
  while (!existsSync(existing)) existing = path.dirname(existing);
  if (realpathSync(existing) !== existing) throw new Error(`${key} must not use symlinked paths`);
  return resolved;
}

// Online profile: Cloudflare Access verification (docs/ONLINE-PILOT-PLAN.md, stage 2).
const ACCESS_KEYS = ["ACCESS_TEAM_DOMAIN", "ACCESS_AUDIENCE", "ACCESS_ALLOWED_EMAILS", "PUBLIC_ORIGIN"];

function accessSettings(values) {
  const team = values.ACCESS_TEAM_DOMAIN || "", audience = values.ACCESS_AUDIENCE || "";
  const emails = (values.ACCESS_ALLOWED_EMAILS || "").split(",").map((e) => e.trim());
  const origin = values.PUBLIC_ORIGIN || "";
  if (!/^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.cloudflareaccess\.com$/.test(team)) {
    throw new Error("ACCESS_TEAM_DOMAIN must be <team>.cloudflareaccess.com");
  }
  if (!/^[0-9a-f]{64}$/.test(audience)) throw new Error("ACCESS_AUDIENCE must be the application's 64-character AUD tag");
  if (!emails.every((e) => /^[^@\s,]+@[^@\s,]+\.[^@\s,]+$/.test(e))) {
    throw new Error("ACCESS_ALLOWED_EMAILS must list one or more email addresses");
  }
  let url;
  try { url = new URL(origin); } catch { url = null; }
  if (!url || url.protocol !== "https:" || url.port || origin !== `https://${url.hostname}`) {
    throw new Error("PUBLIC_ORIGIN must be https://<hostname> with no port, path or slash");
  }
  return { ACCESS_TEAM_DOMAIN: team, ACCESS_AUDIENCE: audience,
    ACCESS_ALLOWED_EMAILS: emails.join(","), PUBLIC_ORIGIN: origin };
}

export function loadConfig(file = process.env.CASCAID_PRODUCTION_CONFIG) {
  if (!file) throw new Error("Set CASCAID_PRODUCTION_CONFIG to an external production.env file; see docs/PRODUCTION-RUNBOOK.md");
  file = absolute(file, "CASCAID_PRODUCTION_CONFIG");
  const permissions = statSync(file);
  if ((permissions.mode & 0o077) || permissions.uid !== process.getuid()) {
    throw new Error("Production configuration must be owned by this account and mode 600");
  }
  const values = parseEnv(readFileSync(file, "utf8"));
  const allowed = new Set(["DEPLOYMENT_PROFILE", "RELEASE_ROOT", "PERSISTENT_ROOT", "NATIVE_MODEL_HOME", "WEB_PORT", "API_PORT", ...ACCESS_KEYS]);
  for (const key of Object.keys(values)) if (!allowed.has(key)) throw new Error(`Unsupported production setting: ${key}`);
  const profile = values.DEPLOYMENT_PROFILE;
  if (profile !== "production-local" && profile !== "production-online") {
    throw new Error("DEPLOYMENT_PROFILE must be production-local or production-online");
  }
  const online = profile === "production-online";
  const access = online ? accessSettings(values) : {};
  if (!online && ACCESS_KEYS.some((key) => key in values)) {
    throw new Error("Access settings are only accepted by the production-online profile");
  }
  const release = absolute(values.RELEASE_ROOT, "RELEASE_ROOT");
  const persistent = absolute(values.PERSISTENT_ROOT, "PERSISTENT_ROOT");
  const modelHome = absolute(values.NATIVE_MODEL_HOME, "NATIVE_MODEL_HOME");
  for (const [name, location] of [["release", release], ["persistent", persistent]]) {
    if (location === path.parse(location).root || within(location, sourceRoot) && location !== sourceRoot) {
      throw new Error(`${name} must not contain the source checkout`);
    }
    if (location !== sourceRoot && within(sourceRoot, location)) throw new Error(`${name} must be outside the source checkout`);
  }
  if (persistent === sourceRoot || within(release, persistent) || within(persistent, release)) {
    throw new Error("Release and persistent directories must be separate");
  }
  if (within(sourceRoot, file) || within(release, file) || within(persistent, modelHome) || within(release, modelHome)) {
    throw new Error("Configuration and model store must be separate from release; model store must also be outside persistent data");
  }
  const port = (key, fallback) => {
    const value = Number(values[key] || fallback);
    if (!Number.isInteger(value) || value < 1024 || value > 65535) throw new Error(`Invalid ${key}`);
    return value;
  };
  const webPort = port("WEB_PORT", 3105), apiPort = port("API_PORT", 8105);
  const configRoot = existsSync(path.join(release, "production-release.json")) ? release : sourceRoot;
  const json = (name) => JSON.parse(readFileSync(path.join(configRoot, "config", name), "utf8"));
  const native = json("native-runtime.json"), speech = json("speech-runtime.json"),
    tts = json("tts-runtime.json"), student = json("finetune.json").student;
  const ports = [webPort, apiPort, native.generation_port, native.embedding_port, speech.port, tts.port, student.port];
  if (new Set(ports).size !== ports.length) throw new Error("Web/API ports conflict with a registered runtime port");
  const stateDir = path.join(persistent, "state");
  if (Buffer.byteLength(path.join(stateDir, "control.sock")) >= 104) {
    throw new Error("PERSISTENT_ROOT is too long for a macOS control socket; use a shorter path");
  }
  // Deliberate allowlist: no inherited development settings, Python paths, proxy
  // variables, NODE_OPTIONS, credentials or model endpoints enter production.
  const env = Object.fromEntries(["HOME", "USER", "LOGNAME", "PATH", "TMPDIR", "LANG"]
    .filter((key) => process.env[key]).map((key) => [key, process.env[key]]));
  Object.assign(env, {
    CASCAID_PRODUCTION_ACTIVE: "1", CASCAID_PRODUCTION_CONFIG: file,
    DEPLOYMENT_PROFILE: profile, ...access, NODE_ENV: "production", NEXT_TELEMETRY_DISABLED: "1",
    PYTHONNOUSERSITE: "1", UV_OFFLINE: "1", HF_HUB_OFFLINE: "1", HF_HUB_DISABLE_TELEMETRY: "1",
    MODEL_BACKEND: "local", SPEECH_BACKEND: "local", TTS_BACKEND: "local", STUDENT_BACKEND: "local",
    INTERPRETER: "cascade", RECORDINGS_ENABLED: "false", NATIVE_MODEL_HOME: modelHome,
    WEB_PORT: String(webPort), API_PORT: String(apiPort), API_BASE_URL: `http://127.0.0.1:${apiPort}`,
    LLM_BASE_URL: `http://127.0.0.1:${native.generation_port}/v1`,
    EMBEDDING_BASE_URL: `http://127.0.0.1:${native.embedding_port}/v1`,
    ASR_BASE_URL: `http://127.0.0.1:${speech.port}`, TTS_BASE_URL: `http://127.0.0.1:${tts.port}`,
    STUDENT_BASE_URL: `http://127.0.0.1:${student.port}`,
    SESSIONS_PATH: path.join(persistent, "sessions"), CLASSIFIER_CACHE: path.join(persistent, "cache/classifier"),
    RECORDINGS_PATH: path.join(persistent, "recordings-disabled"), CASCAID_RUNTIME_STATE_DIR: stateDir,
    SPEECH_STATE_FILE: path.join(stateDir, "speech-state.json"),
    TTS_STATE_FILE: path.join(stateDir, "tts-state.json"), STUDENT_STATE_FILE: path.join(stateDir, "student-state.json"),
  });
  return { file, release, persistent, modelHome, webPort, apiPort, ports, env, stateDir, profile, online,
    publicOrigin: access.PUBLIC_ORIGIN, tokenFile: path.join(stateDir, "internal-token"),
    stateFile: path.join(stateDir, "supervisor.json"), socket: path.join(stateDir, "control.sock"),
    logDir: path.join(persistent, "logs"), native, speech, tts, student };
}
