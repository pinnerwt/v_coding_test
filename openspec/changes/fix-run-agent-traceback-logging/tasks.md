## 1. Red — Failing Test

- [x] 1.1 In `task2/tests/api/test_server.py`, add `test_run_agent_logs_traceback`: patch `agent.loop.loop` to raise `RuntimeError("boom")`, call `_run_agent(run_id, task_req)` with a temp SQLite DB, assert that a `logging.ERROR` record on the `api.server` logger contains `"RuntimeError"` and `"boom"` in `exc_text`, and assert the `traces_runs` row has `status="failed"` and `final` JSON containing `failure.reason="internal error"`.
- [x] 1.2 Run `uv run pytest task2/tests/api/test_server.py::test_run_agent_logs_traceback -x` and confirm it fails (no log record found).

## 2. Green — Minimal Implementation

- [x] 2.1 In `task2/api/server.py`, add `import logging` at the top of the import block.
- [x] 2.2 Add `logger = logging.getLogger(__name__)` as a module-level constant (after imports, before `app = FastAPI()`).
- [x] 2.3 In `_run_agent`'s outer `except Exception` block (currently line 92), insert `logger.exception("agent run failed", extra={"run_id": run_id})` as the first statement, before the inner `try/except writer.close_run` block.
- [x] 2.4 Run `uv run pytest task2/tests/api/test_server.py::test_run_agent_logs_traceback -x` and confirm it passes.

## 3. Regression Check

- [ ] 3.1 Run the full `task2/tests/api/test_server.py` suite and confirm all existing tests still pass.
- [ ] 3.2 Run `uv run ruff check task2/api/server.py task2/tests/api/test_server.py` — fix any lint errors.
- [ ] 3.3 Run `uv run ruff format task2/api/server.py task2/tests/api/test_server.py` — apply formatting.
- [ ] 3.4 Re-run `uv run ruff check task2/api/server.py task2/tests/api/test_server.py` to confirm clean.
