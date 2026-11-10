# Scripts

Do not add a script that downloads or ingests an external source until that source is
permitted in `config/sources.yaml`.

- `npm run dev` creates a private `.env` from `.env.example` if missing, installs locked
  npm/Python dependencies and runs the API and web app on ports 8105/3105.
- `npm run dev:stop` stops the application started by `npm run dev`.
- `npm run production:prepare`, `production:preflight`, `production:start`,
  `production:status`, `production:stop`, `production:smoke` and
  `production:service-file` manage a separate, local production release. See
  [the production runbook](../docs/PRODUCTION-RUNBOOK.md) for configuration and
  macOS service operation. These commands do not publish an internet endpoint.
- `npm run models:install` downloads the pinned llama.cpp runtime and generation model
  into `~/.cache/psychiatryeduai/` and verifies their SHA-256 checksums.
- `npm run models:start` / `models:stop` run and stop the verified local generation server
  (Metal, port 8180, loopback only).
- `npm run speech:install` builds the pinned whisper.cpp server from its checksum-verified
  source with Metal (CMake comes from PyPI via uv) and downloads the default Whisper model;
  `-- --models ggml-small.en.bin,ggml-base.en.bin` adds comparison models.
- `npm run speech:start` / `speech:stop` run and stop it on port 8182 (loopback only);
  `-- --model ggml-small.en.bin` selects another installed model.
- `npm run feedback -- [--summary] data/sessions/<id>.jsonl …` recomputes post-station
  feedback from saved session logs, for batch analysis.
- `npm run experiment:install` / `experiment:start` / `experiment:stop` download and serve a
  pinned evaluation-only comparison model (`config/experiment-models.json`) on port 8183.
- `npm run contracts:generate` regenerates the OpenAPI schema and frontend types after
  contract edits; `npm run contracts:check` detects drift.
- `npm run doctor` reports installed tools; `npm run hardware -- --out artifacts/hardware.json`
  writes a privacy-minimised hardware inventory for the methods section of the paper.
