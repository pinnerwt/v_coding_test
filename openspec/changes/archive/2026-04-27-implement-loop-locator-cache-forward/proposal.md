## Why

Ticket #27 wired a shared `LocatorCache` instance from `run_suite` into `_run_case`, but `_run_case` silently drops it because `loop()` does not accept a cache parameter. The `maintenance-drift-rename` eval case therefore never exercises real cache continuity across v1→v2 in production runs — the proof only works at the unit-test mock level, not through the actual loop.

## What Changes

- Add `locator_cache: LocatorCache | None = None` keyword-only argument to `agent.loop.loop()`.
- When `locator_cache` is provided, thread it into the existing `_locate_with_supervisor` helper inside the loop's `read` tool dispatch path (preserving the supervisor halt/replan flow that ticket #22 tests rely on).
- Embed the cache probe → invalidate → ladder → write cycle inside `_locate_with_supervisor` (shape mirrors `agent.locate.locate()`), reusing `CacheEntry`, `_origin_from_url`, and `_canonical_ax_fingerprint` via lazy imports.
- Emit `LocateEvent` on each cache action inside `_locate_with_supervisor` so `_aggregate_diagnostics` can observe real cache activity:
  - `cache_action="read"` + `outcome="hit"` + `tier="cache"` when a cached entry's fingerprint matches the live page.
  - `cache_action="invalidate"` + `outcome="miss"` + `tier="cache"` when the cached entry mismatches or is `L4_vision`.
  - `cache_action="write"` + `outcome="hit"` + `tier=<resolved tier>` after a fresh ladder resolve writes a new entry.
- Update `scripts/eval._run_case` to forward the `cache` argument it receives into `loop(..., locator_cache=cache)`.
- Add a new fixture test that runs `maintenance-drift-rename` with a real (non-mocked) `loop()` and asserts the v2 trace contains `LocateEvent(cache_action="invalidate")` via `_aggregate_diagnostics`.
- Add a test asserting that when `cache=None`, `loop()` behaves identically to the current API (no regression).

## Capabilities

### New Capabilities

_(none — all changes are incremental wire-ups within existing capabilities)_

### Modified Capabilities

- `agent-loop`: `loop()` signature gains `locator_cache: LocatorCache | None = None`; the loop threads it into `_locate_with_supervisor` on every `read` tool call with an `intent`, and `_locate_with_supervisor` emits `LocateEvent` on cache read-hit, invalidate, and write actions when `trace_writer` + `run_id` are provided.
- `eval-runner`: `_run_case` forwards its `cache` argument into `loop()` via the new `locator_cache` kwarg.

## Impact

- `task2/agent/loop.py` — signature change (backward-compat default `None`) + wire-up inside `_dispatch` or the `read` tool path.
- `task2/scripts/eval.py` — one-line change in `_run_case`: pass `locator_cache=cache` to `loop()`.
- `task2/tests/test_eval.py` — new fixture test for `maintenance-drift-rename` exercising real loop + cache invalidation path.
- No changes to `agent/locate.py`, `agent/locator_cache.py`, or any other module.
- No breaking changes; all existing `loop()` callers (API server, existing tests) pass without modification because the new kwarg defaults to `None`.
