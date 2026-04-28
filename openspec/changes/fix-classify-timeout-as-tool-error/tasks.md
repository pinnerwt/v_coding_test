## 1. Red — Failing Test

- [ ] 1.1 In `task2/tests/test_eval.py`, add `test_classify_failure_tool_error_timeout`: construct a synthetic `ActEvent(outcome="timeout", diff={"error": "TimeoutError on selector X"})` with `status="failed"` and empty validators, call `_classify_failure([ev], [], "failed")`, and assert the result equals `("tool_error", <non-empty string containing "TimeoutError on selector X">)`.
- [ ] 1.2 Run `uv run pytest task2/tests/test_eval.py::test_classify_failure_tool_error_timeout` from `task2/` and confirm it fails with the current code routing through `no_done_emitted` (expected Red).

## 2. Green — Production Fix

- [ ] 2.1 In `task2/scripts/eval.py` at line 201, change the predicate from `ev.outcome == "error"` to `ev.outcome in ("error", "timeout")`.
- [ ] 2.2 Run `uv run pytest task2/tests/test_eval.py::test_classify_failure_tool_error_timeout` — confirm it now passes (Green).
- [ ] 2.3 Run `uv run pytest task2/tests/test_eval.py::test_classify_failure_tool_error` — confirm the existing `outcome="error"` test still passes.

## 3. Full Suite Verification

- [ ] 3.1 Run the full test suite from `task2/`: `uv run pytest` — confirm all tests pass with no regressions.
- [ ] 3.2 Run `uv run ruff check .` from `task2/` — confirm zero lint errors.
