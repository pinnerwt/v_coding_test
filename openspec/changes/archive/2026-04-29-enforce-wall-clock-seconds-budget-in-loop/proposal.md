## Why

`eval/bench/webvoyager_loader.py` declares `_BUDGET = {"steps": 20, "usd": 0.25, "seconds": 120}` for every WebVoyager case, and `scripts/eval.py:_is_near_budget` already treats `seconds` as a real axis. But `agent/loop.py` only enforces `max_steps` — there is no time check inside the step loop. As a result `webvoyager-1` ran 322s (2.7× the 120s budget) before tripping the step ceiling, and a slower run took 373s (3.1× budget). Every overshoot wastes prompt tokens and USD.

## What Changes

- Add an optional `budget_seconds: float | None = None` parameter to `loop()` in `task2/agent/loop.py`.
- Capture `t_loop = time.monotonic()` once before the step loop; at the top of each iteration, return early with `RunResult(status="timeout", reason="seconds_budget", ...)` if `(time.monotonic() - t_loop) >= budget_seconds`.
- Wire `_run_case` in `task2/scripts/eval.py` to pass `budget_seconds=case["budget"].get("seconds")` so production runs honor the per-case `seconds` budget.
- Default behavior with `budget_seconds=None` is unchanged (no new termination path).

## Capabilities

### Modified Capabilities
- `agent-loop`: add a wall-clock time budget as a third termination axis alongside `max_steps` and existing failure modes.

## Impact

- `task2/agent/loop.py`: new parameter, new early-return branch.
- `task2/scripts/eval.py`: `_run_case` passes through `seconds` budget.
- `task2/tests/agent/test_loop.py`: new unit tests covering budget exhaustion and default no-op.
- No public API removed; existing callers keep working unchanged.
