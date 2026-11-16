# Testing

Run `pytest -q` for offline governance, scope filtering, API, ingestion, provider, paper-workspace, and web-serving tests. Tests use temporary directories and synthetic content. Install the package with `python -m pip install -e ".[dev,ingest]"`, then run `python -m ruff check src tests scripts`.

The frontend uses `npm ci`, `npm run typecheck`, and `npm run build` from `frontend/`. The repeatable browser workflow is `npm run test:e2e`; it starts a disposable local memory, serves the built app, exercises synthetic import -> discussion -> approval -> history -> regression, and shuts the test server down with a test-only token. Chromium is downloaded into the workspace when needed.

The browser workflow is deterministic and does not measure real model accuracy. Semantic-provider-unavailable results remain explicitly unavailable. Historical secret scanning and a clean-machine installation rehearsal are still release checks to repeat before publishing a new release.
