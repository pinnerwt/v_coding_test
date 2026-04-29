---
id: 45
slug: surface-tracebacks-run-agent-s-internal
status: active
tier: 4
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related:
- 32
filed_pr: null
merged_pr: null
archived_at: null
trigger: 'migrated from task2/plan.md on 2026-04-29 (ticket #76)'
---

45. **Surface tracebacks from `_run_agent`'s internal-error path.** `task2/api/server.py:93-104` catches `Exception` and writes a `final.failure.reason="internal error"` row, but the `except Exception: pass` block (`api/server.py:103-104`) swallows the underlying traceback entirely — it never reaches the uvicorn log, so a smoke-test failure surfaces only as `status=failed, reason="internal error"`, with no signal as to whether the cause was an LLM 404, a Playwright timeout, an import error, or a database lock. Observed during ticket #32's smoke run: first invocation timed out at 60s, server log contained only INFO request lines, and the diagnostic had to be reproduced by hand-instrumenting `_run_agent` in a one-off script. Add structured error logging on the outer `except Exception` (e.g. `logger.exception("agent run failed", extra={"run_id": run_id})`) so the traceback lands in stderr / uvicorn's structured log, and keep the inner `except Exception: pass` only around the `writer.close_run` retry. Tests: a synthetic `_run_agent(run_id, task_req)` where `loop()` raises `RuntimeError("boom")` produces a stderr line containing `RuntimeError: boom` and the file/line of the raise, while still writing the `final.failure.reason="internal error"` row; the inner-close swallowing is unchanged. *Why useful:* removes a recurring "smoke failed but I can't tell why" debugging round that adds 5–10 min per failed iteration.
