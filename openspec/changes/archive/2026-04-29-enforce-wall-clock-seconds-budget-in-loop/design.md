## Context

`task2/agent/loop.py:755` defines `loop()` with `max_steps` as the only termination cap. Live WebVoyager runs routinely overshoot the documented 120s `seconds` budget by 2-3× because the loop does not check wall-clock time. The benchmark scoring code (`scripts/eval.py:_is_near_budget`) already considers `seconds` a real budget axis, so the asymmetry is purely an enforcement gap.

## Decision

Add `budget_seconds: float | None = None` to `loop()`'s keyword-only parameter list. Inside the loop:

1. Just before `for _ in range(max_steps):`, capture `t_loop = time.monotonic()`.
2. As the **first action** inside each iteration (before `step_num += 1`, before `t0 = time.monotonic()`, before `observe.build_observation`), check `if budget_seconds is not None and (time.monotonic() - t_loop) >= budget_seconds:` and return a `RunResult(status="timeout", reason="seconds_budget", ...)` carrying the metrics accumulated up to but not including this iteration.

The check goes *before* `step_num += 1` so an aborted iteration is never counted as a completed step. `step_breakdown` and `latency_ms_per_step` only ever have entries for *completed* iterations, matching their existing semantics.

Wire it through `scripts/eval.py:_run_case` by reading `case["budget"].get("seconds")` and passing it as `budget_seconds=...`.

## Alternatives considered

- **Check at the *bottom* of each iteration after dispatch.** Rejected: the slow step is the one that overshoots the budget, and we want to bail before incurring its cost — not after.
- **Use a `signal.alarm`-based timeout.** Rejected: requires a single-thread main, breaks under pytest's signal handling, and forks the control flow in a way that makes RunResult metric attribution hard.
- **Add `seconds` to `max_steps` as a tuple.** Rejected: existing callers and tests pass `max_steps` as a positional/keyword int; changing the type is a needless break.

## Risks / Trade-offs

- **Risk:** A genuine successful run that happens to take just over `budget_seconds` would now be cut off. Mitigation: the budget is per-case and was authored with realistic targets (120s for WebVoyager). If the budget needs to grow, that's a data-side fix in `webvoyager_loader.py`, not a loop-side regression.
- **Trade-off:** The check runs on every iteration. Cost is one `time.monotonic()` call (~tens of ns), negligible against the per-step LLM call (seconds).

## Migration

- No public API removed. Default `budget_seconds=None` preserves byte-identical behavior for all existing callers including unit tests and the basic suite (whose cases historically had no `seconds` budget enforced).
- WebVoyager runs after this change will report `status="timeout", reason="seconds_budget"` instead of `status="timeout", reason="max_steps"` (or no `reason`) when the wall clock trips first.
