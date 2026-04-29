## 1. Add failing tests (red)

- [x] 1.1 Add `test_loop_terminates_on_budget_seconds` to `task2/tests/agent/test_loop.py`: stub `LLMClient.chat` sleeps 1.0s and returns a non-terminal `goto` tool call; `loop(..., max_steps=100, budget_seconds=2.5)` returns `RunResult(status="timeout", reason="seconds_budget")` with `2 <= steps <= 4`.
- [x] 1.2 Add `test_loop_no_budget_seconds_default_unchanged` asserting `loop(...)` without `budget_seconds` still completes normally on a 2-step happy-path stub.
- [x] 1.3 Add `test_run_case_threads_seconds_budget`: monkeypatch `agent.loop.loop` to capture kwargs and assert `_run_case` passes `budget_seconds=case["budget"]["seconds"]`.
- [x] 1.4 Run pytest, confirm new tests fail with the expected reasons.

## 2. Implement (green)

- [x] 2.1 Add `budget_seconds: float | None = None` to `loop()` signature in `task2/agent/loop.py`.
- [x] 2.2 Capture `t_loop = time.monotonic()` immediately before the `for _ in range(max_steps):` line.
- [x] 2.3 Insert the early-return check as the first statement inside the iteration; return `RunResult(status="timeout", reason="seconds_budget", ...)` preserving cumulative metrics.
- [x] 2.4 Update `task2/scripts/eval.py:_run_case` to pass `budget_seconds=case["budget"].get("seconds")`.
- [x] 2.5 Re-run pytest; all new tests pass.

## 3. Verify and clean up

- [x] 3.1 Run `cd task2 && uv run ruff check .` — clean.
- [x] 3.2 Run `cd task2 && uv run pytest` — full suite green except known pre-existing failures.
- [x] 3.3 Smoke a basic-suite case end-to-end against the local Qwen endpoint.
- [x] 3.4 `/opsx:verify` passes.
- [x] 3.5 `/simplify` makes no edits or only trivial cleanup.
