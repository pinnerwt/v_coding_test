## Context

Tickets #1–#13 deliver a fully working agent loop with structured trace persistence. The entire stack lives inside `task2/agent/` as pure Python — no HTTP surface exists yet. Ticket #14 wraps it with FastAPI: a `POST /tasks` endpoint that accepts a natural-language task, runs the agent asynchronously, and exposes `GET /tasks/{id}` and `GET /tasks/{id}/trace` to read the result. This is the integration layer required before the eval runner (ticket #15) and Dockerfile (ticket #18).

Existing code style constraints:
- `TraceWriter` (from `agent/trace.py`) is the single persistence API; the API layer MUST reuse it, not write SQLite directly.
- `loop()` (from `agent/loop.py`) is the entrypoint for the agent; the API layer calls it unchanged.
- No hardcoded LLM endpoint; `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` are read from env.
- `uv run pytest`, `uv run ruff check .` from `task2/`.
- No comments/docstrings in production code except one-line *why* comments.

## Goals / Non-Goals

**Goals:**

- `POST /tasks` validates the request body, returns `{ "id": "<ulid>" }` immediately (async — the agent runs in a `BackgroundTask`).
- `GET /tasks/{id}` returns the run's final state from SQLite: `status`, `result`, `evidence`, `totals`, or `{ "status": "running" }` while the background task is still executing.
- `GET /tasks/{id}/trace` streams the JSONL event log for the run as `application/x-ndjson` (one JSON object per newline-terminated line).
- `GET /` serves a minimal inline HTML page with a task-submit form and a polling `<pre>` block.
- A shared `api/db.py` module reads `DB_PATH` from env (defaulting to `./agent_tasks.db`) and exposes the path string; both the write path (TraceWriter) and read path (GET endpoints) use this same path.
- All endpoints tested with `TestClient` (sync), patching the agent loop at the module boundary. No live browser, no live LLM in tests.
- `fastapi`, `uvicorn[standard]`, `python-ulid` added as runtime deps.

**Non-Goals:**

- WebSocket or Server-Sent Events streaming of live trace updates (polling is sufficient for the demo).
- Authentication or rate limiting.
- Task cancellation or deletion.
- Multi-tenant or multi-user isolation.
- Screenshot storage or serving of `screenshot_ref` blobs.
- Pagination of `GET /tasks/{id}/trace` (full stream on every request is fine for the demo).
- Schema validation of `expect_schema` against the task result (deferred to ticket #15).

## Decisions

### Decision 1: `BackgroundTask`, not a worker queue

`POST /tasks` spawns the agent loop via FastAPI's `BackgroundTasks`. The response returns the `run_id` immediately; the loop runs in the same process on the uvicorn thread pool. This avoids a Redis/Celery dependency while being sufficient for the single-request-at-a-time Zeabur deployment.

**Alternative considered**: a separate subprocess per request via `asyncio.create_subprocess_exec`. Rejected — too much overhead for a demo; the browser is the bottleneck, not the Python runtime.

**Alternative considered**: a proper task queue (Celery + Redis). Rejected — adds two new services and a dependency for no benefit at demo scale.

**Concurrency note**: `TraceWriter` is not thread-safe (SQLite WAL is per-connection). Each background task creates its own `TraceWriter` instance for the duration of the run. Multiple simultaneous runs will have separate `TraceWriter` connections to the same SQLite file — this is safe because WAL mode allows one writer at a time, and each run writes to a different `run_id` partition. Under load, tasks will queue at the SQLite write lock; acceptable at demo scale.

### Decision 2: `python-ulid` for run IDs

The plan specifies `run_id: string // ULID`. The trace schema already uses string IDs; `python-ulid` generates sortable, URL-safe IDs with millisecond precision. The decision in ticket #12 deferred this; at the API layer, callers need a URL path segment that sorts lexicographically by creation time, making ULID the right choice.

**Alternative**: `uuid4`. Rejected — not lexicographically sortable by time; cosmetically inconsistent with the plan spec.

### Decision 3: `GET /tasks/{id}` reads from SQLite directly, not in-memory state

The background task writes the `Run` header and events to SQLite via `TraceWriter`. The GET endpoint reads from the same SQLite file via a read-only query. This means there is no shared in-memory state between the background task and the read path — the SQLite file is the source of truth.

**Alternative**: an in-memory dict `{run_id: RunState}` shared between the background task and GET handlers. Rejected — not restart-safe; breaks when Zeabur restarts the container (the in-progress run is lost but the write path was already writing to SQLite anyway).

### Decision 4: Run status while in progress

`TraceWriter.open_run()` is called before the background task starts, with `status=None`. The `GET /tasks/{id}` endpoint checks `traces_runs.status IS NULL` and returns `{ "status": "running" }`. When the run completes, `TraceWriter.close_run()` sets `status` to the terminal value. This avoids a separate `tasks` table and leverages the existing schema.

**Alternative**: a separate `tasks` table with an `in_progress` flag. Rejected — redundant with `traces_runs.status IS NULL`.

### Decision 5: `GET /tasks/{id}/trace` streams JSONL from SQLite

The endpoint queries `traces_events` ordered by `seq` for the given `run_id` and returns each `payload TEXT` row as a newline-terminated line. `Content-Type: application/x-ndjson`. FastAPI's `StreamingResponse` with a generator makes this trivial without loading all events into memory.

**Alternative**: return a JSON array `[{event}, ...]`. Rejected — breaks incremental streaming; clients can't start rendering the timeline until the entire response is received.

### Decision 6: Inline HTML at `GET /`

A single static HTML string is returned by the root route — no template engine, no `Jinja2` dependency. The page has a `<form>` that POSTs to `/tasks` via `fetch`, then polls `GET /tasks/{id}` every 2 seconds until `status` is not `"running"`, then renders the result as pretty-printed JSON in a `<pre>` block.

**Alternative**: a Jinja2 template. Rejected — overkill for a single page with no dynamic server-side values; a literal string is simpler and has no additional deps.

### Decision 7: Test strategy — `TestClient` with loop patched at module boundary

Tests use `fastapi.testclient.TestClient` (synchronous). The agent loop (`agent.loop.loop`) is patched via `unittest.mock.patch("api.server.loop")` to return a canned `RunResult` without launching Playwright or an LLM. The `TraceWriter` uses `:memory:` SQLite in tests to avoid file I/O.

**Why patch `api.server.loop` not `agent.loop.loop`**: patching the name as imported into `api.server` is the standard Python mock pattern; it intercepts the call at the call site, not at the definition site.

**Alternative**: integration test with a real loop against fixture pages. Deferred to eval runner (ticket #15).

### Decision 8: `api/db.py` for shared DB path

A tiny `api/db.py` module exposes `get_db_path() -> str` (reads `DB_PATH` env, defaults to `./agent_tasks.db`) and `open_writer() -> TraceWriter` (convenience factory). Both the server module and any future CLI tools import from here, avoiding scattered `os.environ.get("DB_PATH", ...)` calls.

**Alternative**: inline `os.environ.get` at every call site. Rejected — two call sites (write path and test setup) would need to stay in sync.

## Risks / Trade-offs

- **Single SQLite file for locator cache + traces**: `task2/agent/locator_cache.py` uses its own SQLite path (also configurable). They are separate files by default. If both are pointed at the same file, the schema tables do not conflict (`locator_cache` vs `traces_*`). The API does not change the locator cache path.
- **BackgroundTask vs. asyncio event loop**: `agent.loop.loop()` and `agent.browser.Browser` use the synchronous Playwright API (sync_playwright). FastAPI's `BackgroundTasks` run in a thread pool when the function is synchronous, which is correct. If the function signature is `async def`, Playwright's sync API will deadlock. The background task function MUST be a plain `def`, not `async def`.
- **No run timeout enforcement in the API layer**: `loop()` accepts `max_steps`; `RunBudget.seconds` is stored in the trace but not enforced by a `threading.Timer` in this ticket. A stuck browser will hold the background thread indefinitely. Acceptable for demo; noted for production hardening.
- **`GET /tasks/{id}/trace` returns all events for completed runs**: for long runs this could be a large response. No pagination in scope; the demo budget caps at 20 steps.

## Open Questions

(none — all decisions resolved above)
