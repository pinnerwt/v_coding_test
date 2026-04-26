## Why

The agent loop and trace writer (tickets #9–#13) are fully functional but have no HTTP surface: there is no way for external callers or the Zeabur deployment to submit a task, track its progress, or retrieve the structured trace. This change wires everything together behind a FastAPI server — the final integration layer before the eval runner and Dockerfile.

## What Changes

- New package `task2/api/` with `__init__.py` and `server.py`: FastAPI application exposing `POST /tasks`, `GET /tasks/{id}`, `GET /tasks/{id}/trace`, and a minimal HTML page at `GET /` for manual testing.
- `POST /tasks` accepts `{ "task": str, "expect_schema"?: object, "budget"?: {...} }`, validates the payload, spawns the agent loop as a FastAPI `BackgroundTask`, persists the `Run` via `TraceWriter`, and returns `{ "id": "<ulid>" }` immediately (async, non-blocking).
- `GET /tasks/{id}` returns the `Run` final state (status, result, evidence, totals) from SQLite, or `{ "status": "running" }` if still in progress.
- `GET /tasks/{id}/trace` streams the JSONL event log for the run (one JSON object per line, `Content-Type: application/x-ndjson`).
- `GET /` serves a minimal HTML page (static string, no template engine) with a form to submit a task and a `<pre>` block that polls `GET /tasks/{id}` until terminal.
- New `task2/api/db.py`: shared SQLite connection factory (`get_db_path()` reads `DB_PATH` env var, defaults to `./agent_tasks.db`). Reused by both `TraceWriter` and the read path.
- New test file `task2/tests/api/test_server.py`: TDD-first, uses `httpx.AsyncClient` + `fastapi.testclient.TestClient` (sync), no real browser, no real LLM. The agent loop is patched at the module boundary.
- `fastapi`, `uvicorn[standard]`, and `python-ulid` added as runtime dependencies via `uv add`.

## Capabilities

### New Capabilities

- `api-server`: HTTP front door for the browser automation agent. `POST /tasks` enqueues a run (background task, returns ULID immediately). `GET /tasks/{id}` returns run state. `GET /tasks/{id}/trace` streams JSONL events. `GET /` serves a minimal task-submission HTML page.

### Modified Capabilities

(none — `trace.py`, `loop.py`, `browser.py`, `llm.py`, `locate.py`, `supervisor.py` are unchanged by this ticket)

## Impact

- **Code**: new `task2/api/__init__.py`, `task2/api/server.py`, `task2/api/db.py`; new `task2/tests/api/__init__.py`, `task2/tests/api/test_server.py`.
- **Dependencies**: `fastapi`, `uvicorn[standard]`, `python-ulid` added to `task2/pyproject.toml` runtime deps. `httpx` already present (used in tests via `fastapi.testclient`).
- **Env vars**: `DB_PATH` (path to SQLite file, defaults to `./agent_tasks.db`), `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` (already documented in plan.md).
- **Existing modules**: `agent/trace.py` and `agent/loop.py` are consumed but not modified. The server is the integration layer, not a rewrite.
- **Zeabur**: `uvicorn task2.api.server:app --host 0.0.0.0 --port $PORT` is the entry point for the deployed service.
