# CascAid local production runtime

Stage 1 of [the online pilot plan](ONLINE-PILOT-PLAN.md) is an isolated,
loopback-only production deployment (`production-local`). Stage 2 adds the
`production-online` profile: the same runtime, still listening only on loopback,
with every API request requiring a verified Cloudflare Access sign-in. It is
published through an outbound Cloudflare Tunnel; see **Online access** below.

**Commands**

| Command | Behaviour |
|---|---|
| `npm run production:prepare` | Snapshots deployment inputs into a new release, installs locked dependencies from local caches and builds Next.js |
| `npm run production:preflight` | Checks platform, all ports, release identity, installed asset checksums and private directories |
| `npm run production:start` | Supervises local models/speech, prepares classifiers, warms a synthetic interview, then starts the production web server |
| `npm run production:status` | Queries the supervisor and checks end-to-end readiness; nonzero exit means not ready |
| `npm run production:stop` | Asks the identified supervisor over its private socket to stop its own process groups |
| `npm run production:smoke` | Runs a synthetic interview (through the web proxy locally; on the API port online), exercises speech/ASR and feedback, then removes that synthetic session |
| `npm run production:service-file` | Writes a macOS LaunchAgent plist; does not install or load it |
| `npm run test:production` | Runs deployment/configuration/process tests using temporary data |

All commands require `CASCAID_PRODUCTION_CONFIG`, an absolute path to a private
configuration file. They never read the development `.env` into production.
Startup performs no installation, model downloads or web build. Preparation is
also offline: populate the npm/uv caches through your normal reviewed dependency
installation first if they are missing. Model installation remains a separate
explicit workflow using the registered install scripts.

**One-time setup**

For a dedicated host, create a standard macOS service account and sign in as that
account. Install the pinned Node/Python tools and registered model/speech assets
for it. Do not run the application as root. The development Mac can be used for a
rehearsal in the current account; this does not prove unattended boot recovery or
isolation from that account's other programs.

Copy `config/production.env.example` outside the checkout and edit all paths:

```sh
mkdir -p "$HOME/CascAid"
chmod 700 "$HOME/CascAid"
cp config/production.env.example "$HOME/CascAid/production.env"
chmod 600 "$HOME/CascAid/production.env"
```

Use literal absolute paths in the file (no `~`, shell variables or interpolation).
`RELEASE_ROOT` must name a new, absent directory outside the checkout. Persistent
data, configuration and installed models are separate from the release. Keep the
persistent path short enough for a macOS Unix socket (under 104 bytes including
`/state/control.sock`). The model store can be the existing verified local cache
for a same-account rehearsal. A dedicated account should own its own installation.

Only the settings in the examples are accepted. `DEPLOYMENT_PROFILE` must be
`production-local` or `production-online` (which also requires the four Access settings
in `config/production-online.env.example`); model backends are forced to local, recording is disabled,
and all listeners/endpoints use `127.0.0.1`. There is no online bypass flag.

```sh
export CASCAID_PRODUCTION_CONFIG="$HOME/CascAid/production.env"
npm run production:prepare
```

Preparation copies application code, configuration, prompts, authored cases and
topic/tone classifier data, including current uncommitted application edits. It
does not copy the repository history, sessions, recordings, evaluation sets or
development `.env`. Installed avatar assets under `apps/web/public` are included;
install them beforehand if needed. Dependency locks, source hashes, Node version
and build ID are recorded in `production-release.json`. Treat each release as
immutable: changing code, paths, ports or Node requires preparing a new release.
Failed preparation leaves its directory for diagnosis; select a fresh release
name for the next attempt rather than overwriting it.

**Switch from development to production**

On the current Mac, use mutually exclusive windows. Stop only the services you
started through this project's launchers:

```sh
npm run dev:stop
npm run models:stop
npm run speech:stop
npm run student:stop
npm run tts:stop
npm run production:preflight
npm run production:start
```

The last command stays in the foreground. Use a second terminal with the same
`CASCAID_PRODUCTION_CONFIG` to inspect or stop it. A busy port produces an error;
production never kills or adopts an unknown service to make room. Changing web
ports does not permit simultaneous model use: registered model ports remain fixed
at 8180–8184, and both launchers and API URLs derive from those registry values.
Do not train or evaluate models during production sessions.

First startup can spend several minutes building classifier embeddings from the
authored training lines. Progress states are `starting`, `warming-classifiers`,
`warming`, then `ready`. The cache is retained outside the release for subsequent
starts. A synthetic interview warms generation, speech, transcription and feedback
before the web listener opens. Its session file is removed; no human audio is used.

After readiness:

```sh
npm run production:status
npm run production:smoke
```

Open `http://127.0.0.1:3105` for the default web port. Uvicorn uses one worker with
no reload, and Next runs `start`, not `dev`. Production readiness requires local
generation, embedding, student, recognition and voice services. A service failure
closes admission by stopping the web server and restarts the stack, at most twice
per invocation. Exhausting retries requires manual investigation and a new start.

**Online access (stage 2, owner only)**

What the code enforces in `production-online`:

- Every API route requires a `Cf-Access-Jwt-Assertion` that verifies against the
  team's published keys (`https://<team>.cloudflareaccess.com/cdn-cgi/access/certs`):
  RS256 only, the configured issuer and audience, unexpired, with a subject and an
  email in `ACCESS_ALLOWED_EMAILS`. A bare email header is never trusted. Service
  tokens (no email) are refused. Keys are cached for an hour; if Cloudflare cannot be
  reached, previously fetched keys remain usable for six hours, after which every
  request is refused with 503 until a fetch succeeds.
- State-changing requests must carry `Origin: <PUBLIC_ORIGIN>`. Bodies are counted as
  they arrive (64 KiB JSON; one minute of audio for transcription). Each identity may
  make 120 state-changing requests a minute. Responses are `no-store`.
- API documentation and recording endpoints do not exist in this profile.
- The web proxy forwards only `/backend/api/*`. `/health` and `/ready` are reachable on
  loopback alone and are the only routes without a sign-in.
- The supervisor creates a random secret on each start, gives it to the API processes
  only and keeps it in `state/internal-token` (mode 600, removed on stop). Warm-up and
  `production:smoke` present it on the API's loopback port. The web proxy refuses any
  request that carries that header, so it cannot be used through the tunnel.

This stage is for the owner only. Sessions are not yet isolated between users (stage
3), so do not add other emails to Access or to `ACCESS_ALLOWED_EMAILS`.

One-time setup, in this order. Access must protect the hostname before DNS routes
to it:

1. Use a domain whose DNS is managed by Cloudflare. In Zero Trust, note the team
   domain and enable an identity method (one-time PIN by email is sufficient).
2. Create a self-hosted Access application for `cascaid.<domain>` covering the whole
   hostname, with a single Allow policy for the owner's email and no Bypass rules.
   Copy its Application Audience (AUD) tag.
3. `brew install cloudflared`, `cloudflared tunnel login`, then
   `cloudflared tunnel create cascaid`. Copy `config/cloudflared.example.yml` to
   `~/.cloudflared/cascaid.yml` and fill in the tunnel ID, credentials file and
   hostname. Keep the final `http_status:404` rule. The service must be the web
   port, never the API or model ports.
4. Copy `config/production-online.env.example` to a new private configuration
   (`chmod 600`), fill in the Access values and a new `RELEASE_ROOT`, then
   `production:prepare`, `production:preflight` and `production:start` as above.
5. `cloudflared tunnel --config ~/.cloudflared/cascaid.yml ingress validate`, then
   `cloudflared tunnel route dns cascaid cascaid.<domain>` and
   `cloudflared tunnel --config ~/.cloudflared/cascaid.yml run cascaid`.

**Starting and stopping on demand**

On a shared Mac, run the pilot only when needed:

```sh
npm run online:stop      # if anything is running from a previous session
npm run dev:stop; npm run models:stop; npm run speech:stop; npm run student:stop; npm run tts:stop
npm run online:start     # several minutes; returns once CascAid and the tunnel are up
npm run online:status
npm run online:stop      # tunnel first, then CascAid; frees all ports
```

These default to `~/CascAid/production-online.env` when `CASCAID_PRODUCTION_CONFIG` is
unset; `CLOUDFLARED` and `CASCAID_TUNNEL_CONFIG` override the binary and the tunnel
configuration (default `~/.cloudflared/config.yml`). Before loading any model,
`online:start` checks that the tunnel publishes only `http://127.0.0.1:<WEB_PORT>` for
the public hostname and ends with a 404 catch-all. It opens the tunnel only after CascAid
reports ready. Both run as launchd jobs loaded for the current login session, so they
continue after the terminal closes. Nothing is installed in `~/Library/LaunchAgents`, so
neither starts at login or after a reboot. Logs: `PERSISTENT_ROOT/logs/` (`tunnel.log`,
`launchd.log` and the service logs).

Completion checks (record them in the pilot plan):

- Over mobile data, sign in and complete a voice station including feedback.
- In a private window, the hostname and `https://cascaid.<domain>/backend/api/cases`
  show the Access sign-in, not CascAid data.
- `curl -s -o /dev/null -w "%{http_code}" -H "Cf-Access-Jwt-Assertion: x" http://127.0.0.1:8105/api/cases`
  prints 401.
- From another network, ports 3105, 8105 and 8180–8184 on the router's public address
  are closed. No port forwarding is configured.
- Stopping `cloudflared` makes the hostname unavailable without touching local data.
  Restarting it after a broadband reconnect restores access.

Emergency shutdown: stop `cloudflared`, or disable the tunnel's public hostname in
the Cloudflare dashboard. Production keeps running on loopback, and sessions are
untouched. Remote audio and text pass through Cloudflare, which terminates HTTPS;
models, sessions and transcripts stay on this Mac.

**macOS service operation**

Generate and inspect the LaunchAgent as the intended account:

```sh
npm run production:service-file
plutil -lint "$HOME/CascAid/var/uk.cascaid.production.plist"
```

The command prints the actual location if `PERSISTENT_ROOT` differs. The plist
contains absolute Node/release/configuration paths and the current executable
search path. Regenerate it after changing those paths or the intended account.
Do not run a foreground supervisor and the LaunchAgent simultaneously.

To test it in the signed-in account without installing login persistence:

```sh
launchctl bootstrap "gui/$(id -u)" "$HOME/CascAid/var/uk.cascaid.production.plist"
npm run production:status
npm run production:smoke
npm run production:stop
launchctl bootout "gui/$(id -u)/uk.cascaid.production"
```

After successful testing, placing the plist in that account's
`~/Library/LaunchAgents/` provides startup on login. `RunAtLoad` is enabled;
`KeepAlive` is disabled so launchd does not defeat the supervisor's retry limit.
After an intentional stop, use `launchctl kickstart gui/<uid>/uk.cascaid.production`
to restart a loaded job. Remove/unload the LaunchAgent to disable it permanently.

This is a user-session LaunchAgent, not a pre-login daemon. FileVault may require
unlocking the disk and the service account must log in after reboot. Test Metal,
MLX, TTS and sleep/restart behaviour on the final host. Do not enable automatic
login or disable disk encryption merely to achieve unattended restart. Keep the
Mac awake during availability windows; a UPS and wired networking are recommended
for booked use. Reboot/power-loss recovery remains an operator rehearsal.

**Data, diagnosis and recovery**

`PERSISTENT_ROOT` contains private `sessions/`, `cache/classifier/`, `state/`,
`logs/` and a reserved `database/` directory (booking database is a later stage).
Sessions stay on this Mac. No backup destination or retention deletion is enabled
by stage 1. Do not assume development session backups cover these new directories.

Use `production:status`, then the relevant log in `logs/` and native launcher logs
in `state/`. Supervisor service logs keep the previous startup's log; native
launcher logs are truncated on restart. Continuous log rotation, retention and
backup/restore automation belong to stage 5. Do not publish runtime logs: third
party runtimes may emit diagnostic request information.

The stop command uses a private control socket and deployment ID, never a PID
from disk as authority to kill a process. If the process was force-killed, its
socket/lock can remain and descendants may still be running. A failed control
connection does not prove all children are stopped. Inspect the recorded release,
process command lines and listeners; stop only confirmed owned services. Once
all owned processes are gone and ports are free, remove the stale
`state/supervisor.lock`, `state/control.sock`, `state/supervisor.json` and (online)
`state/internal-token`, then run
preflight again. Do not clear a lock while another supervisor is starting.

Rollback means stop, restore the previous configuration/release and start it.
Preserve persistent sessions. Stage 1 does not migrate their format or create a
booking schema; later schema migrations need their own rollback procedure.

To return to development, stop/unload production, then run `models:start`,
`speech:start`, `student:start`, `tts:start` and `dev` in separate terminals as
before. The two deployments do not share `.env`, mutable session directories or
runtime state. Existing model files can be reused sequentially.

**Validation record**

The implementation is tested with temporary configuration/ports/processes and
production settings/readiness tests. Record the completed host smoke tests and
any baseline-suite failures in the online pilot plan. Successful local production
operation does not establish authentication, booking isolation, internet access,
clinical validation or unattended operation after a power failure.
