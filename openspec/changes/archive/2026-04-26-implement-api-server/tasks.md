## 1. Dependencies and package scaffold

- [x] 1.1 From `task2/`, run `uv add fastapi "uvicorn[standard]" python-ulid` to add runtime deps; confirm `pyproject.toml` and `uv.lock` are updated.
- [x] 1.2 Create `task2/api/__init__.py` (empty file — marks the package).
- [x] 1.3 Create `task2/tests/api/__init__.py` (empty file).
- [x] 1.4 Verify the package is discoverable: from `task2/`, run `uv run python -c "import api"` and confirm no ImportError.

## 2. Red — Failing tests (db module)

- [x] 2.1 Create `task2/tests/api/test_server.py`. Add `from api.db import get_db_path` — this import MUST fail with `ModuleNotFoundError` until `api/db.py` exists. Confirm the failure with `uv run pytest tests/api/test_server.py -x`.
- [x] 2.2 Add `test_get_db_path_default`: monkeypatch removes `DB_PATH` from env; call `get_db_path()`; assert result is `"./agent_tasks.db"`.
- [x] 2.3 Add `test_get_db_path_custom`: monkeypatch sets `DB_PATH="/tmp/custom.db"`; call `get_db_path()`; assert result is `"/tmp/custom.db"`.

## 3. Green — Implement `api/db.py`

- [x] 3.1 Create `task2/api/db.py`. Implement `get_db_path() -> str`: reads `os.environ.get("DB_PATH", "./agent_tasks.db")`. Import `os`. No other logic.
- [x] 3.2 From `task2/`, run `uv run pytest tests/api/test_server.py -x` and confirm the db tests pass.

## 4. Red — Failing tests (POST /tasks)

- [x] 4.1 In `task2/tests/api/test_server.py`, add `from api.server import app` — this MUST fail until `api/server.py` exists. Confirm failure.
- [x] 4.2 Add `test_post_tasks_returns_id`: create a `TestClient(app)` with `DB_PATH` set to a temp SQLite path (monkeypatch); patch `api.server.loop` to return `RunResult(status="succeeded", result={"ok": True}, evidence={"url": "http://x", "text_snippet": "x"}, verifier={"ok": True, "reasons": []})`; POST `{"task": "do a thing"}` to `/tasks`; assert response status 200 and body contains `"id"` key with a non-empty string value.
- [x] 4.3 Add `test_post_tasks_missing_task_returns_422`: POST `{}` to `/tasks`; assert response status 422.
- [x] 4.4 Add `test_post_tasks_empty_task_returns_422`: POST `{"task": ""}` to `/tasks`; assert response status 422.
- [x] 4.5 Add `test_post_tasks_creates_run_record`: after the POST, open a raw `sqlite3.connect` to the temp DB and query `SELECT run_id FROM traces_runs`; assert exactly one row exists with the returned `id`.
- [x] 4.6 From `task2/`, run `uv run pytest tests/api/test_server.py -x` and confirm these tests fail (ImportError or assertion errors).

## 5. Red — Failing tests (GET /tasks/{id})

- [x] 5.1 Add `test_get_task_running`: open a `TraceWriter` on the temp DB, call `open_run(run)` with `status=None` and a known `run_id`; then GET `/tasks/{run_id}`; assert response 200 with body `{"status": "running"}`.
- [x] 5.2 Add `test_get_task_completed`: call `open_run` then `close_run` with `status="succeeded"`, `final={"result": {"ok": True}, "evidence": {...}, "failure": None}`, `totals={...}`; GET `/tasks/{run_id}`; assert response 200 with body containing `"status": "succeeded"`.
- [x] 5.3 Add `test_get_task_not_found`: GET `/tasks/nonexistent-id`; assert response 404.

## 6. Red — Failing tests (GET /tasks/{id}/trace)

- [x] 6.1 Add `test_get_trace_returns_ndjson`: open a `TraceWriter`, call `open_run` + `append_event` for two events (e.g., an `ObservationEvent` at seq=1 and a `DoneEvent` at seq=2); GET `/tasks/{run_id}/trace`; assert status 200 and `Content-Type` header contains `application/x-ndjson`; split response text by `"\n"` (filter empty), assert 2 lines.
- [x] 6.2 Add `test_get_trace_events_ordered_by_seq`: same setup with events appended in seq order; assert first line parses to an event with `seq == 1`, second to `seq == 2`.
- [x] 6.3 Add `test_get_trace_not_found`: GET `/tasks/nonexistent-id/trace`; assert 404.
- [x] 6.4 Add `test_get_trace_empty_for_running_run`: open a `TraceWriter`, call `open_run` only (no events); GET `/tasks/{run_id}/trace`; assert 200 with empty body.

## 7. Red — Failing tests (GET /)

- [x] 7.1 Add `test_root_returns_html`: GET `/`; assert status 200 and `Content-Type` contains `text/html`; assert response text contains `<form` and `task`.

## 8. Green — Implement `api/server.py`

- [x] 8.1 Create `task2/api/server.py`. Add `from __future__ import annotations` and imports: `os`, `sqlite3`, `fastapi` (`FastAPI`, `BackgroundTasks`, `HTTPException`), `fastapi.responses` (`HTMLResponse`, `StreamingResponse`), `pydantic` (`BaseModel`, `field_validator`), `ulid` (`ULID`), `agent.trace` (`Run`, `RunBudget`, `RunLLM`, `RunFinal`, `RunTotals`, `TraceWriter`), `agent.loop` (`loop`, `RunResult`), `agent.llm` (`LLMClient`), `agent.browser` (`Browser`), `api.db` (`get_db_path`), `datetime` (`datetime`, `timezone`).
- [x] 8.2 Define `TaskRequest(BaseModel)` with `task: str` and `expect_schema: dict | None = None` and `budget: dict | None = None`. Add a `field_validator("task")` that raises `ValueError` if `task.strip()` is empty.
- [x] 8.3 Define `app = FastAPI()`.
- [x] 8.4 Implement `_run_agent(run_id: str, task_req: TaskRequest) -> None` (plain `def`, not `async def`): constructs `LLMClient` from env, opens `Browser`, opens `TraceWriter(get_db_path())`, calls `loop(task_req.task, browser, llm_client)`, calls `writer.close_run(...)` with the `RunResult` fields. Wraps the whole body in a try/finally so `TraceWriter.close()` and `Browser` are always cleaned up.
- [x] 8.5 Implement `POST /tasks` route: instantiate `run_id = str(ULID())`, build a `Run` object with `status=None`, `ended_at=None`, `final=None`, `totals=None`, call `TraceWriter(get_db_path()).open_run(run)`, add `_run_agent` as a `BackgroundTask`, return `{"id": run_id}`.
- [x] 8.6 Implement `GET /tasks/{run_id}` route: query `traces_runs` via `sqlite3.connect(get_db_path())` for the row; if not found return 404; if `status IS NULL` return `{"status": "running"}`; else return the full run payload as a dict.
- [x] 8.7 Implement `GET /tasks/{run_id}/trace` route: query `traces_events` for the `run_id` ordered by `seq ASC`; if the run does not exist in `traces_runs` return 404; return a `StreamingResponse` with a generator that yields each `payload + "\n"`, media type `application/x-ndjson`.
- [x] 8.8 Implement `GET /` route: return an `HTMLResponse` with an inline HTML string containing a `<form>` that uses `fetch` to POST to `/tasks`, then polls `GET /tasks/{id}` every 2 seconds until `status != "running"`, rendering the result in a `<pre>`.
- [x] 8.9 From `task2/`, run `uv run pytest tests/api/test_server.py -x` and confirm all API tests pass.

## 9. Full test suite (green bar)

- [x] 9.1 From `task2/`, run `uv run pytest` (full suite including all existing agent tests) and confirm zero regressions.

## 10. Lint and format

- [x] 10.1 From `task2/`, run `uv run ruff check --fix .` to auto-fix any lint issues.
- [x] 10.2 From `task2/`, run `uv run ruff format .` to auto-format changed files.
- [x] 10.3 From `task2/`, run `uv run ruff check .` and confirm it exits clean (zero errors, zero warnings).

## 11. Refactor under green

- [x] 11.1 Review `_run_agent` for cleanup correctness: confirm the `try/finally` block closes both the `TraceWriter` and the `Browser` even when `loop()` raises an unexpected exception. Add a test if this path is untested.
- [x] 11.2 Verify that `api/server.py` contains no hardcoded `LLM_BASE_URL`, `localhost:8090`, or model name strings outside of `os.environ.get(...)` default expressions. Run `grep -n "localhost:8090\|openai.com\|anthropic.com" task2/api/server.py` and confirm empty output.
- [x] 11.3 Confirm `api/db.py` and `api/server.py` have no module-level docstrings or function docstrings (per the no-docstrings rule). One-line `#` *why* comments are allowed.
