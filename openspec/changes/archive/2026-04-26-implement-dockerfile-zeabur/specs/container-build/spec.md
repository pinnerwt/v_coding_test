## ADDED Requirements

### Requirement: Dockerfile builds a runnable agent service image
The `task2/Dockerfile` SHALL produce a Docker image that runs the FastAPI agent service when started. The image SHALL use `mcr.microsoft.com/playwright/python:v1.58.0-noble` as the base (Chromium ships in the base image at `/ms-playwright`, exposed via `PLAYWRIGHT_BROWSERS_PATH`). Dependencies SHALL be installed with `uv sync --no-dev --frozen` (no pip; uv creates a `.venv` inside the image). The entrypoint SHALL launch `.venv/bin/uvicorn api.server:app --host 0.0.0.0 --port 8000`. No comments or docstrings SHALL appear in the Dockerfile.

#### Scenario: Image starts and serves HTTP
- **WHEN** `docker run -p 8000:8000 <image>` is executed with a reachable `LLM_BASE_URL` env var
- **THEN** the container listens on port 8000 and responds to `GET /` with HTTP 200

#### Scenario: uv is used for dep install, not pip
- **WHEN** the image is built
- **THEN** `pip` is not invoked at any layer; only `uv` is used to resolve and install Python packages into `.venv/`

#### Scenario: Playwright Chromium is available inside image
- **WHEN** the image is built
- **THEN** `python -c "from playwright.sync_api import sync_playwright; sync_playwright().__enter__().chromium.launch(headless=True).close()"` exits 0 inside the container

### Requirement: .dockerignore excludes non-essential files
`task2/.dockerignore` SHALL exclude `.venv/`, `**/__pycache__/`, `**/*.pyc`, `**/*.db`, `eval/results/`, `.git/`, and `*.egg-info/` from the build context to keep the image lean.

#### Scenario: Build context does not include .venv
- **WHEN** the image is built from `task2/`
- **THEN** `.venv/` is not present in the image filesystem

#### Scenario: Build context does not include DB files
- **WHEN** the image is built from `task2/`
- **THEN** no `*.db` files from the host are copied into the image
