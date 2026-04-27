## Why

When `_run_agent` in `api/server.py` catches the outer `Exception`, it silently swallows the traceback — the `except Exception: pass` block around `writer.close_run` absorbs everything, so a smoke-test failure surfaces only as `status=failed, reason="internal error"` with no Python traceback in the uvicorn log. Diagnosing the actual cause (LLM 404, Playwright timeout, import error, DB lock) requires hand-instrumenting the server, adding 5–10 min of wasted debugging per failed smoke run.

## What Changes

- Add `logger.exception("agent run failed", extra={"run_id": run_id})` in the outer `except Exception` block of `_run_agent` so the full traceback reaches stderr / uvicorn's structured log.
- Keep the inner `except Exception: pass` only around `writer.close_run` (the retry path) — it continues to suppress close failures silently.
- Add a module-level `logger = logging.getLogger(__name__)` to `api/server.py`.
- Add a regression test: a synthetic `_run_agent` call where `loop()` raises `RuntimeError("boom")` asserts that stderr contains `RuntimeError: boom` and the raise site file/line, while the `final.failure.reason="internal error"` row is still written and `writer.close_run` swallowing is unchanged.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `api-server`: The `_run_agent` internal-error path now emits a structured log record containing the full exception traceback before writing the `final.failure.reason="internal error"` row.

## Impact

- `task2/api/server.py`: add `import logging`, `logger = logging.getLogger(__name__)`, one `logger.exception(...)` call in the outer `except Exception` block.
- `task2/tests/api/test_server.py`: new test `test_run_agent_logs_traceback` that patches `loop` to raise, captures `logging` output, asserts traceback presence and DB row content.
- No API surface changes, no new dependencies, no breaking changes.
