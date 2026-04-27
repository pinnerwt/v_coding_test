## Why

Ticket #27 wired a shared `LocatorCache` instance from `run_suite` into `_run_case`, but `_run_case` silently drops it because `loop()` does not accept a cache parameter. The `maintenance-drift-rename` eval case therefore never exercises real cache continuity across v1→v2 in production runs — the proof only works at the unit-test mock level, not through the actual loop.

## What Changes

- Add `locator_cache: LocatorCache | None = None` keyword-only argument to `agent.loop.loop()`.
- When `locator_cache` is provided, thread it into every `locate()` call inside the loop's `read` tool dispatch path.
- Update `scripts/eval._run_case` to forward the `cache` argument it receives into `loop(..., locator_cache=cache)`.
- Add a new fixture test that runs `maintenance-drift-rename` with a real (non-mocked) `loop()` and asserts the v2 trace contains `LocateEvent(cache_action="invalidate")` via `_aggregate_diagnostics`.
- Add a test asserting that when `cache=None`, `loop()` behaves identically to the current API (no regression).

## Capabilities

### New Capabilities

_(none — all changes are incremental wire-ups within existing capabilities)_

### Modified Capabilities

- `agent-loop`: `loop()` signature gains `locator_cache: LocatorCache | None = None`; the loop threads it into the locate path on every `read` tool call with an `intent`.
- `eval-runner`: `_run_case` forwards its `cache` argument into `loop()` via the new `locator_cache` kwarg.

## Impact

- `task2/agent/loop.py` — signature change (backward-compat default `None`) + wire-up inside `_dispatch` or the `read` tool path.
- `task2/scripts/eval.py` — one-line change in `_run_case`: pass `locator_cache=cache` to `loop()`.
- `task2/tests/test_eval.py` — new fixture test for `maintenance-drift-rename` exercising real loop + cache invalidation path.
- No changes to `agent/locate.py`, `agent/locator_cache.py`, or any other module.
- No breaking changes; all existing `loop()` callers (API server, existing tests) pass without modification because the new kwarg defaults to `None`.
