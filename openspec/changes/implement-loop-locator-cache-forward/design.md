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

### Decision 1: Thread cache through `locate()` facade rather than duplicating cache logic in `_dispatch`

`agent.locate.locate()` already implements the full cache probe → ladder → write cycle. Rather than duplicating that logic inside `_dispatch` in `loop.py`, we replace the direct calls to `locate_l1` / `locate_l2` (via `_locate_with_supervisor`) with a call to `locate(page, intent, cache=locator_cache)` inside the `read` branch of `_dispatch`.

**Alternative considered:** Keep `_locate_with_supervisor` and plumb cache into it. Rejected because that would duplicate the cache probe/invalidate/write logic already living in `locate()`, and would require touching `locate.py` to expose cache-aware L1/L2 helpers.

**Trade-off:** The `locate()` facade runs L1→L2→L3→L4 on a miss; `_locate_with_supervisor` currently only runs L1→L2. Replacing the call with `locate()` implicitly enables L3/L4 fallbacks. This is acceptable: it expands the locate capability in the loop, is already tested at the locate level, and is not a regression. The supervisor integration (halt → replan) becomes slightly simpler — locate misses are handled by `locate()` raising `LocatorMiss` if the full ladder fails.

### Decision 2: `locator_cache` parameter on `loop()` defaults to `None` with no internal default cache construction

The ticket text states: "when `cache=None`, `loop()` constructs / uses its current default cache (no behavior change for the existing API server path)." Because the current loop has no cache at all, `None` is the correct default and means "no cache." We do not construct a throwaway in-memory cache when `None` is passed — that would silently change behavior for callers who pass nothing.

### Decision 3: `_dispatch` receives `locator_cache` via parameter, not closure

`_dispatch` is a module-level function. Rather than introducing a closure or class, we add `locator_cache: LocatorCache | None = None` as a parameter to `_dispatch`. The `loop()` function already calls `_dispatch(tool_name, args, browser, supervisor)` — extend it to `_dispatch(tool_name, args, browser, supervisor, locator_cache)`.

## Risks / Trade-offs

- [Risk] Replacing `_locate_with_supervisor` with `locate()` changes the supervisor integration path: the supervisor no longer mediates between L1 and L2. → Mitigation: the new test exercises the cache invalidation path end-to-end and proves the locate call works. Existing supervisor unit tests in `test_loop.py` still pass because they mock the LLM and browser at a level that does not reach the locate dispatch.
- [Risk] Introducing `locate()` in the loop opens L3 and L4 tiers. → Mitigation: this is a feature not a bug; the ladder is already well-tested. We note in the tasks to verify no existing loop test breaks.
- [Risk] The new real-loop test requires a Playwright browser fixture. → Mitigation: use the existing `playwright_chromium` and `fixture_server` conftest fixtures already used in `test_drift.py`. The test is `fixture: True` so CI runs it without `--live`.

## Open Questions

_(none — the design is fully specified by the ticket requirements)_
