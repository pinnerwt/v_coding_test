## Context

`agent.loop.loop()` is the central execution engine for browser automation runs. `agent.locate.locate()` already accepts an optional `cache: LocatorCache | None = None` parameter (introduced in a prior ticket), but `loop()` never passes one — it calls `locate_l1` and `locate_l2` directly (via `_locate_with_supervisor`) rather than going through the top-level `locate()` facade.

Ticket #27 wired a shared `LocatorCache` from `run_suite` → `_run_case(cache=...)`, but `_run_case` drops it before calling `loop()` because `loop()` has no cache parameter. The `maintenance-drift-rename` eval case therefore only exercises cache continuity through mocked assertions, not through the real code path.

## Goals / Non-Goals

**Goals:**
- `loop()` gains `locator_cache: LocatorCache | None = None` kwarg.
- When `locator_cache` is not `None`, it is threaded into the `read` tool dispatch path so that every `locate()` call during a run uses the shared cache.
- `_run_case` forwards its received `cache` argument as `locator_cache` to `loop()`.
- A new test exercises the full `maintenance-drift-rename` invalidation path using a real loop (mocked LLM only, real locate + real cache) and asserts `cache_events["invalidations"] >= 1` via `_aggregate_diagnostics`.
- All existing `loop()` callers pass unchanged (the new kwarg defaults to `None`).

**Non-Goals:**
- Changing `agent/locate.py` or `agent/locator_cache.py`.
- Exposing the cache through the API server (that path already does not pass a cache; the `None` default keeps it correct).
- Adding a file-backed persistent cache (still `:memory:` only for eval; no scope creep).
- Replacing `_locate_with_supervisor` with the full `locate()` facade for L1/L2 dispatch — only the `read` intent path needs the cache.

## Decisions

### Decision 1: Thread cache through `_locate_with_supervisor` rather than swapping it for `locate()`

We add `cache: LocatorCache | None = None` to `_locate_with_supervisor` and embed a probe → invalidate → L1/L2-with-supervisor → write cycle there, mirroring the pattern in `agent.locate.locate()` (probe by `(origin, intent)`, validate via canonical AX fingerprint, write on success). The `_dispatch` `read` branch keeps calling `_locate_with_supervisor`, now with `cache=locator_cache`.

**Alternative considered (rejected):** Replace the call with `locate(page, intent, cache=locator_cache)`. This was the original design but it removes `supervisor.handle()` from the read path entirely, breaking 5 existing tests in `tests/agent/test_loop.py` that depend on the supervisor halt → replan flow (`test_supervisor_halt_triggers_replan_event`, `test_second_supervisor_halt_returns_failed`, `test_loop_does_not_terminally_fail_on_unrelated_error_after_replan`, `test_replan_does_not_leave_orphan_tool_call_in_message_history`, `test_loop_with_trace_writer_replan_seq_after_initial_seq`). Ticket #28 requires "existing `loop()` tests still pass with no signature-change fixups required", so preserving `_locate_with_supervisor` is load-bearing.

**Trade-off:** A small amount of cache logic now lives in `loop.py` alongside its sibling in `locate.py`. We mitigate by reusing the existing helpers (`CacheEntry`, `_origin_from_url`, `_canonical_ax_fingerprint`) via lazy imports — no duplicated logic, just one extra call site of the same primitives. L3/L4 fallbacks are intentionally not enabled in the loop path (out of scope for this ticket).

### Decision 2: `locator_cache` parameter on `loop()` defaults to `None` with no internal default cache construction

The ticket text states: "when `cache=None`, `loop()` constructs / uses its current default cache (no behavior change for the existing API server path)." Because the current loop has no cache at all, `None` is the correct default and means "no cache." We do not construct a throwaway in-memory cache when `None` is passed — that would silently change behavior for callers who pass nothing.

### Decision 3: `_dispatch` receives `locator_cache` via parameter, not closure

`_dispatch` is a module-level function. Rather than introducing a closure or class, we add `locator_cache: LocatorCache | None = None` as a parameter to `_dispatch`. The `loop()` function already calls `_dispatch(tool_name, args, browser, supervisor)` — extend it to `_dispatch(tool_name, args, browser, supervisor, locator_cache, trace_writer=..., run_id=...)` so that emission has access to both the writer and the run identifier.

### Decision 4: Trace emission lives in `_locate_with_supervisor`, not in `LocatorCache`

`_aggregate_diagnostics` reads `LocateEvent` rows to compute `cache_events = {hits, invalidations, misses}` for the eval acceptance test. Without emission anywhere, those counts stay at zero even when the cache invalidates correctly. We considered emitting from `LocatorCache.put/get/invalidate`, but that couples a pure storage primitive to the trace schema (a layering inversion: the cache cannot know the `run_id` or which `step_id` it belongs to). Emission therefore lives at the call site in `_locate_with_supervisor`, where `trace_writer` and `run_id` are already in scope through the `_dispatch` thread.

A new helper `_emit_locate_event` follows the same shape as `_emit_plan_event` (lazy seq allocation via `trace_writer.next_seq(run_id)`, no-op when `trace_writer is None or run_id is None`). Three emission points exist, exactly mirroring the three cache state transitions:

1. **Read hit** — entry found and live fingerprint matches → `cache_action="read"`, `outcome="hit"`, `tier="cache"`, `chosen={role, selector, ax_fingerprint}`.
2. **Invalidate** — entry exists but live fingerprint mismatches OR entry is `L4_vision` → `cache_action="invalidate"`, `outcome="miss"`, `tier="cache"`, `chosen=None`.
3. **Write** — fresh ladder resolve completes and we `cache.put(...)` → `cache_action="write"`, `outcome="hit"`, `tier=<resolved tier from ladder>`, `chosen={role, selector, ax_fingerprint}`.

We deliberately do not emit on plain L1/L2 ladder hits when there is no cache interaction — those are not cache events and would inflate `_aggregate_diagnostics` counts incorrectly.

## Risks / Trade-offs

- [Risk] Embedding cache logic in `_locate_with_supervisor` duplicates the pattern in `agent.locate.locate()`. → Mitigation: reuse `CacheEntry`, `_origin_from_url`, and `_canonical_ax_fingerprint` directly via lazy imports; the loop side calls the same primitives, no new helpers.
- [Risk] The new real-loop test requires a Playwright browser fixture. → Mitigation: use the existing `playwright_chromium` and `fixture_server` conftest fixtures already used in `test_drift.py`. The test is `fixture: True` so CI runs it without `--live`.

## Open Questions

_(none — the design is fully specified by the ticket requirements)_
