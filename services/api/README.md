# Local application API

Use `npm run dev` from the repository root to start the API and web app. The service
uses the uv-managed Python 3.12 environment and the ignored root `.env`.

- `cases.py` — versioned station cases with a hidden fact state and disclosure rules,
  validated against the pinned CASC blueprint (skills, subdivisions, specialties, timings).
- `sources.py` — the source registry policy (`config/sources.yaml`).
- `models/` — provider-neutral protocols, normalized errors, local llama.cpp adapters
  and deterministic fakes. `selection.py` verifies the pinned local generation model.
- `health.py` — readiness of the registry, cases and (in local mode) the generation model.
- `cancellation.py` — cancels model work when a client disconnects.

Endpoints: `/health`, `/ready`, `/api/status`, `/api/cases` (summaries only, never hidden
facts) and `/api/sources`.

From the repository root:

```sh
npm run test:api
npm run lint:api
npm run format:api:check
npm run contracts:generate     # after changing API/Pydantic contracts
npm run contracts:check
```

No real model or external service is called by the test suite.
