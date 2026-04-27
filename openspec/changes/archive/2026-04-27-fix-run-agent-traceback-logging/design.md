## Context

`task2/api/server.py` runs the agent loop in a FastAPI background task via `_run_agent`. The function has two exception handlers:

1. **Outer** `except Exception` (lines 92–103): catches any failure from `LLMClient`, `Browser`, or `loop()`, then attempts to write a `final.failure.reason="internal error"` row via `writer.close_run`.
2. **Inner** `except Exception: pass` (lines 102–103): wraps only the `writer.close_run` retry so a DB failure during close does not propagate.

Currently neither handler logs anything. The outer handler re-raises nothing and passes no information to uvicorn, so every internal error is silent. Uvicorn's access log shows the `POST /tasks` 200 response but no subsequent error line.

The fix is a one-line `logger.exception(...)` call inside the outer `except` block, before the inner `try/except`. Python's `logging.exception` captures the live exception info automatically (no need to pass `sys.exc_info()` explicitly) and writes a `ERROR`-level record with the full traceback to the logger's handlers — which uvicorn routes to stderr by default.

## Goals / Non-Goals

**Goals:**
- Full exception traceback from `_run_agent` always appears in stderr / uvicorn's log when any unhandled exception escapes the `loop()` call.
- The `final.failure.reason="internal error"` DB row continues to be written (existing behavior preserved).
- The inner `except Exception: pass` continues to swallow `writer.close_run` failures silently (existing behavior preserved).
- A regression test validates all three properties above without touching a live LLM or browser.

**Non-Goals:**
- Structured JSON logging format changes (out of scope; uvicorn defaults are acceptable).
- Propagating the exception type or message into the `final.failure` payload (separate concern, different ticket).
- Log level configuration (uvicorn default `INFO` threshold plus `ERROR` record is sufficient).

## Decisions

### D1: Use `logging.getLogger(__name__)` at module level

`__name__` resolves to `api.server`, which is the natural logger name for this module and integrates with standard Python logging hierarchy. Alternatives considered:
- `logging.getLogger("uvicorn.error")`: would route into uvicorn's own logger, but that couples application code to the ASGI framework's internal namespace — fragile if uvicorn renames its loggers.
- `print(..., file=sys.stderr)`: works but bypasses the logging framework, losing log-level filtering and structured output options downstream.

### D2: Call `logger.exception(...)` not `logger.error(..., exc_info=True)`

Both are equivalent at runtime. `logger.exception` is the idiomatic form when the call site is inside an `except` block; it signals intent more clearly to future readers.

### D3: Keep `extra={"run_id": run_id}` on the log call

Adding `run_id` as a structured extra field costs nothing and makes log correlation trivial when multiple concurrent runs are in flight. The field appears in the `LogRecord` and in any structured log formatter that exposes extras (e.g., `python-json-logger`).

### D4: Test via `logging.handlers.MemoryHandler` / `caplog` fixture, not stderr capture

pytest's `caplog` fixture (or `assertLogs`) intercepts `logging` records before they reach any handler, which is cleaner than redirecting `sys.stderr`. The test asserts on the record `message` and `exc_text` fields. This also avoids fighting with uvicorn's own stderr interception in test context.

## Risks / Trade-offs

- [Risk] High-frequency agent crashes could flood logs. → Mitigation: these are background tasks that run once per HTTP request; flooding implies a deployment-level problem that should be visible, not hidden.
- [Risk] Test relies on `caplog` capturing the `api.server` logger. → Mitigation: `caplog` captures all loggers by default; the test sets `propagate=True` on the logger if needed, which is the pytest default.
- [Trade-off] We do not surface the traceback in the HTTP response or in the `final` payload — callers still see only `"internal error"`. This is intentional: tracebacks in API responses are a security concern and a separate design question.
