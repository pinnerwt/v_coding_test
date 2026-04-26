## 1. Red — Failing smoke test

- [x] 1.1 Register the `docker` pytest marker in `task2/pyproject.toml` under `[tool.pytest.ini_options] markers`; verify `uv run pytest --markers` lists it (run from `task2/`)
- [x] 1.2 Create `task2/tests/test_docker_smoke.py` with a `@pytest.mark.docker` test that attempts to build the Docker image from `task2/Dockerfile` (which does not exist yet) and asserts the response to `POST /tasks` contains an `id` field — run `uv run pytest -m docker task2/tests/test_docker_smoke.py` and confirm it fails because `task2/Dockerfile` is missing
- [x] 1.3 Confirm the test is NOT collected by the default `uv run pytest` run (no `-m docker` flag)

## 2. Dockerfile and .dockerignore

- [x] 2.1 Create `task2/.dockerignore` excluding `.venv/`, `**/__pycache__/`, `**/*.pyc`, `**/*.db`, `eval/results/`, `.git/`, and `*.egg-info/` — no comments in the file
- [x] 2.2 Create `task2/Dockerfile`: base image `mcr.microsoft.com/playwright/python:v1.58.0-noble`; install `uv` (official installer, single RUN layer); copy `pyproject.toml` and `uv.lock`; run `uv sync --no-dev --system`; copy source; run `playwright install chromium --with-deps`; expose port 8000; entrypoint `uvicorn api.server:app --host 0.0.0.0 --port 8000` — no comments in the Dockerfile
- [x] 2.3 Run `docker build -t vici-task2:smoke task2/` from the repo root and confirm it exits 0
- [x] 2.4 Run `docker run --rm -e LLM_BASE_URL=http://localhost:8090 -p 8000:8000 vici-task2:smoke` and verify `GET http://localhost:8000/` returns HTTP 200 (use curl; stop container after)

## 3. Green — Smoke test passes

- [x] 3.1 In `test_docker_smoke.py`, add a `_start_mock_llm` helper: a `threading.Thread`-based HTTP server on a random port that returns a canned OpenAI-compatible chat-completions response with a `done` tool call (matching the schema `agent/llm.py` expects — refer to `task2/tests/agent/test_llm.py` for the exact request/response shape); the `done` args must include `result` and `evidence` fields
- [x] 3.2 In the smoke test, resolve the host's Docker bridge IP (use `host.docker.internal` on macOS/Windows; on Linux use `172.17.0.1` or inspect `docker0`) and pass it as `LLM_BASE_URL` so the container can reach the mock server
- [x] 3.3 Wire up the full smoke test flow: `docker build` → `docker run` (detached, with `LLM_BASE_URL` pointing to mock, `DB_PATH=/tmp/smoke.db`) → wait for `GET /` to return 200 (poll with timeout) → `POST /tasks` with `{"task": "Read the page heading and return it as title"}` → assert response status 200 and `"id" in response_json` → stop and remove the container in a `finally` block
- [x] 3.4 Run `uv run pytest -m docker task2/tests/test_docker_smoke.py -v` and confirm it passes

## 4. Zeabur deployment config

- [x] 4.1 Create `task2/zeabur.json` with `buildType: "dockerfile"`, `dockerfilePath: "task2/Dockerfile"` (relative to repo root), `port: 8000`, and `envs` listing `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` as required/optional keys — values left blank (filled in Zeabur dashboard); no comments in the file
- [ ] 4.2 Deploy the service on Zeabur: connect repo, set build root, set env vars (`LLM_BASE_URL` → reachable OpenAI-compatible endpoint, `LLM_MODEL`, `LLM_API_KEY` if needed), trigger deploy, wait for health check to pass
- [ ] 4.3 Verify deployed endpoint: `curl -X POST https://<zeabur-url>/tasks -H 'Content-Type: application/json' -d '{"task":"ping"}' | jq .id` returns a non-empty string

## 5. README and prompts

- [x] 5.1 Update `task2/README.md`: add a Deployment section with the `docker build` + `docker run` commands (including all required env vars), the live Zeabur URL (replace placeholder with actual URL from step 4.3), and a note about `DB_PATH` for optional volume persistence
- [x] 5.2 Ensure `prompts/task2/` exists and contains the key LLM prompts used by the agent (plan, decide, locate-rerank, locate-vision, classify-failure, verify-evidence); add any missing prompt files — the reviewers read these
- [x] 5.3 Run `uv run ruff check . && uv run ruff format --check .` from `task2/` and confirm clean (no production code was changed, but double-check)
- [x] 5.4 Run the full non-docker test suite (`uv run pytest` from `task2/`) and confirm still green
