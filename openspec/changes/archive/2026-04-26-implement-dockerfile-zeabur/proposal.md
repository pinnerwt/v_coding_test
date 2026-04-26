## Why

Task 2 is complete in code but not yet deployed; the repo-root CLAUDE.md requires a running Zeabur URL. A Dockerfile and Zeabur service definition are the minimum additions to ship the FastAPI agent service to a public endpoint.

## What Changes

- Add `task2/Dockerfile` — multi-stage build using the official Playwright Python base image; installs deps with `uv`, runs `playwright install chromium --with-deps`, launches `uvicorn api.server:app`.
- Add `task2/.dockerignore` — excludes `.venv`, `__pycache__`, `*.pyc`, `*.db`, `eval/results/`, `.git`.
- Add `task2/zeabur.json` — minimal Zeabur service descriptor pointing at the `task2/` Dockerfile, declaring required env vars and the exposed port.
- Add `task2/tests/test_docker_smoke.py` — TDD red-first test that builds the image locally, runs a container, POSTs to `/tasks` with a fixture task, and asserts the response contains a run `id`.
- Update `task2/README.md` — add docker run command, Zeabur URL placeholder, and env var reference.

## Capabilities

### New Capabilities

- `container-build`: Dockerfile + .dockerignore that produces a runnable image of the Task 2 agent service.
- `zeabur-deploy`: Zeabur service descriptor and env var mapping that allows one-click deploy from the Dockerfile.
- `docker-smoke-test`: End-to-end smoke test that builds and runs the image locally, hitting `POST /tasks` with a fixture task.

### Modified Capabilities

## Impact

- `task2/Dockerfile` and `task2/.dockerignore` — new files, no existing code changes.
- `task2/zeabur.json` — new file.
- `task2/tests/test_docker_smoke.py` — new test file; runs outside the normal `pytest` fast suite (marked `slow` / `docker`); requires Docker daemon and a reachable `LLM_BASE_URL` at test time.
- `task2/README.md` — updated with deployment instructions.
- No changes to `agent/` or `api/` production code.
