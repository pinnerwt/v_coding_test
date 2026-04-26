## Context

The Task 2 agent service (`task2/`) is fully implemented and tested in Python with FastAPI, Playwright, and a local-SQLite trace store. It runs locally via `uv run uvicorn api.server:app`. The repo-root CLAUDE.md requires a Zeabur deployment for each task. This design covers making the service container-ready and deployable.

Constraints (from CLAUDE.md and plan.md):

- `uv` is the only allowed package manager; no pip inside the image.
- No hardcoded LLM provider — `LLM_BASE_URL` must be a runtime env var.
- Playwright Chromium with system dependencies must be present in the image.
- Python version must match `pyproject.toml` (`>=3.11`).
- No comments or docstrings in production code under `task2/`.
- TDD: failing test written before Dockerfile exists.
- Smallest thing that works — no abstractions for hypothetical second callers.

## Goals / Non-Goals

**Goals:**

- Single `Dockerfile` in `task2/` that produces a self-contained image running the FastAPI service.
- `.dockerignore` that keeps the image lean (excludes `.venv`, caches, DB files, eval results).
- `zeabur.json` at `task2/` root that Zeabur reads to deploy the service from the Dockerfile with required env vars declared.
- `task2/tests/test_docker_smoke.py` — TDD smoke test: build image → run container → `POST /tasks` with fixture task → assert `id` in response.
- `task2/README.md` updated with docker run command and Zeabur URL.

**Non-Goals:**

- Multi-stage build optimisation beyond what is needed to run Playwright.
- Docker Compose or orchestration for local dev (out of scope).
- Persistent volume configuration in the Dockerfile (documented in README, configured in Zeabur dashboard).
- Pushing to a registry as part of CI (not asked for in the brief).
- Changing any `agent/` or `api/` production code.

## Decisions

### Base image: `mcr.microsoft.com/playwright/python:v1.58.0-noble`

**Chosen over** a plain `python:3.11-slim` + manual Playwright install, because the MS Playwright image bundles all browser system deps and is the canonical upstream. Version-pinned to match the `playwright>=1.58.0` dep in `pyproject.toml` — avoids browser/driver mismatch.

Alternatives considered:
- `python:3.11-slim` + `playwright install-deps` — more brittle; MS image is tested together.
- `mcr.microsoft.com/playwright/python:latest` — plan.md mentions this, but pinning is safer for reproducible builds.

### Dependency install: `uv` inside the image (no-venv, system install)

`uv sync --no-dev --system` installs runtime deps into the system Python so `uvicorn api.server:app` resolves without activating a venv. `uv` binary is installed via the official `uv` installer (single curl layer) before the `uv sync` step. Alternatives: `pip install -r requirements.txt` — violates repo tooling rules.

### `playwright install chromium --with-deps` in Dockerfile

Run as a `RUN` layer after `uv sync` so Chromium is present in the image. `--with-deps` installs OS packages. The MS base image already carries many of these, so this is a fast layer that guarantees correctness.

### Zeabur config: `zeabur.json` (not `zeabur.toml`)

Zeabur supports both; JSON is simpler to write without a TOML library and is the format used in most Zeabur examples. Declares `buildType: "dockerfile"`, `dockerfilePath: "task2/Dockerfile"` (relative to repo root), exposed port 8000, and the required env var keys (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`).

### Exposed port: 8000

`uvicorn` defaults to 8000; `api/server.py` does not override this. The Zeabur descriptor declares `port: 8000`. The smoke test also hits port 8000 on the container.

### Smoke test strategy: `subprocess` + `httpx`, marked `docker`

The test calls `docker build` and `docker run` via `subprocess`, waits for the server to be ready, then uses `httpx` to `POST /tasks`. It uses the `eval_heading.html` fixture served by a Python `http.server` inside the container (or simply submits a fixture-resident task URL) — see specs for details. Marked `@pytest.mark.docker` and excluded from the default `pytest` run via `pyproject.toml` marker filter; CI can opt in via `pytest -m docker`.

The test does NOT mock Docker; it exercises the real build and run path. The LLM call is avoided by using the fixture-only eval case `fixture-heading` which the agent should complete without a live LLM (the test can set `LLM_BASE_URL` to a mock server started in the test, to avoid requiring a real Qwen endpoint).

### `LLM_BASE_URL` in Zeabur: env var, no default

The image must not bake in `localhost:8090`. `api/server.py` already reads `LLM_BASE_URL` from the environment with a fallback to `http://localhost:8090` — the Zeabur deployment overrides this via the env var set in the Zeabur dashboard. The `zeabur.json` lists the var name so the deployer knows to fill it in.

## Risks / Trade-offs

- **Docker build time in CI** — Playwright base image is large (~1 GB). Mitigation: smoke test is opt-in (`-m docker`); normal CI skips it.
- **Qwen endpoint not reachable from Zeabur** — The deployed service depends on an external LLM endpoint. Mitigation: documented in README; deployer must set `LLM_BASE_URL` to a reachable endpoint (e.g. a public OpenAI-compatible API).
- **SQLite persistence on Zeabur** — Zeabur containers are ephemeral; DB is lost on redeploy without a persistent volume. Mitigation: acceptable for demo; documented in README. The `DB_PATH` env var (already in `api/db.py`) allows mounting a volume.
- **Smoke test requires Docker daemon** — Not available in all CI environments. Mitigation: marker-gated, skipped by default.

## Migration Plan

1. Write failing `test_docker_smoke.py` (red).
2. Create `Dockerfile`, `.dockerignore`, `zeabur.json` (green).
3. Run `docker build` locally to verify.
4. Run `pytest -m docker` to confirm smoke test passes.
5. Push to Zeabur via dashboard ("Deploy from GitHub" → select repo, set env vars).
6. Update `task2/README.md` with the live URL.

## Open Questions

- Zeabur dashboard requires a manual deploy step; the Zeabur URL will be a placeholder in specs/tasks until the deployer fills it in after the first successful deploy.
- The smoke test mock-LLM approach (respx or a tiny `http.server` that returns a canned tool-call response) needs to be decided at implementation time — the spec requires it returns a valid `RunResult`; the exact mock shape depends on `agent/llm.py`'s request format (already tested in `test_llm.py`).
