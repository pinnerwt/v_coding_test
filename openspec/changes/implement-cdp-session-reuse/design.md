## Context

`observe._ax_nodes` (lines 30–64 of `task2/agent/observe.py`) builds the AX tree used for every agent observation. It currently calls `page.context.new_cdp_session(page)` at line 33 and `cdp.detach()` in the finally block at line 42 on every call. With N=10 steps that is 10 CDP protocol handshakes where 1 would suffice.

`Browser` (task2/agent/browser.py) is the natural owner of the per-page cache: it already holds `_page`, `_context`, and the Playwright browser reference. It is a context manager and its `__exit__` is the correct place to release resources.

The `_ax_nodes` function is private (single underscore prefix, only called from `build_observation`). Its current signature is `_ax_nodes(page)`. This will change to `_ax_nodes(browser)` so it can access the cache.

## Goals / Non-Goals

**Goals:**
- One CDP session opened per page object lifetime.
- `Browser.__exit__` detaches all cached sessions without raising.
- Page navigation that produces a new `page` object invalidates the old cache entry and opens a fresh session on the next observation call.
- All existing `test_observe.py` tests pass unchanged.
- The dict returned by `build_observation` is identical in shape and semantics.

**Non-Goals:**
- Caching sessions for multiple simultaneous pages (the current `Browser` holds one `_page` at a time).
- Persisting sessions across `Browser.__exit__` / `__enter__` cycles.
- Thread safety (the agent loop is single-threaded by design).
- Any change to the public API surface of `Browser` beyond the new `_cdp_sessions` internal attribute.

## Decisions

### Decision 1: Cache key — use `id(page)` (Python object identity)

**Choice**: Key the cache with `id(page)` — Python's built-in object identity integer.

**Alternatives considered**:
- `page.guid` (Playwright-assigned string): also stable per page object, but requires a live Playwright context to inspect and adds an attribute-access on every call.
- The `page` object itself as a dict key: requires `page` to be hashable; Playwright `Page` objects are not guaranteed hashable across versions.
- A monotonic counter on `Browser`: simpler but does not survive an accidental double-assignment of `_page`.

**Rationale**: `id(page)` is always available, requires no Playwright internals, and correctly identifies object identity. Because Python reuses memory addresses after objects are garbage-collected, a stale entry for a dead page could theoretically collide with a new page's `id`. This is mitigated by the invalidation strategy below.

### Decision 2: Invalidation — evict on every `_ax_nodes` call when `id(page)` changes

**Strategy**: `build_observation` already holds a reference to `browser._page`. Inside `_ax_nodes(browser)`, compare `id(browser._page)` against the keys in `browser._cdp_sessions`. If the current page's id is not a key, the cached sessions for any *other* ids are stale (the page was replaced). Detach and remove them before opening a fresh session for the current page.

This is safe because `Browser` holds at most one active `_page` at a time. Any id not matching the current `_page` is dead.

### Decision 3: `_ax_nodes` signature change — accept `Browser` not `page`

`_ax_nodes(browser)` instead of `_ax_nodes(page)`. The function already lives in `observe.py` and has no external callers (it is module-private). `build_observation` passes `browser` directly. The fallback test `test_build_observation_falls_back_when_new_cdp_session_raises` uses a `fake_browser` namespace — it must gain a `_cdp_sessions: dict` attribute for the new code path, but the test needs no behavioral change because the `new_cdp_session` exception path is exercised the same way.

### Decision 4: `__exit__` error handling — log + continue

`Browser.__exit__` iterates `self._cdp_sessions.values()` and calls `detach()` on each. Any `Exception` from `detach()` is caught and suppressed (no logging, consistent with the rest of `__exit__`'s pattern of silent cleanup). The cache dict is cleared unconditionally after the loop.

### Decision 5: No docstrings or comments in production code

Per repo `CLAUDE.md`, production code carries no docstrings or inline comments. The design document and specs are the record of intent.

## Risks / Trade-offs

- **`id()` address reuse**: If Python recycles the memory address of a garbage-collected page for a new page, the cache lookup would return a stale session. Mitigation: the invalidation step in Decision 2 clears all entries whose id does not match the *current* `browser._page` on every call, so a reused address will only survive if the old page and new page happen to be the same object — which is impossible if the old one was garbage-collected.
- **`fake_browser` in existing tests**: The fallback test constructs a `SimpleNamespace` without `_cdp_sessions`. The updated `_ax_nodes` must handle this gracefully. The implementation will use `getattr(browser, "_cdp_sessions", None)` with a `None` branch that falls through to a plain `new_cdp_session` call, preserving the existing fallback behavior and keeping the test unchanged.
- **Single page assumption**: The cache is keyed by page id but `Browser` is only designed for one page at a time. If that ever changes, the eviction strategy (clear all non-current ids) would need revisiting. This risk is accepted: the ticket is explicitly scoped to the current single-page design.

## Migration Plan

1. Add `self._cdp_sessions: dict = {}` to `Browser.__init__`.
2. Add `__exit__` cleanup loop after the existing `context.close()` call (before it, actually — sessions must be detached before the context closes to avoid Playwright errors).
3. Update `_ax_nodes` signature from `(page)` to `(browser)`, implement cached lookup with eviction.
4. Update `build_observation` to pass `browser` to `_ax_nodes` instead of `browser._page`.
5. Update `fake_browser` namespace in `test_build_observation_falls_back_when_new_cdp_session_raises` to include `_cdp_sessions={}` — this is a minimal fixture update, not a behavioral test change.

Rollback: the change is entirely internal to `observe.py` and `browser.py`; reverting to the per-call pattern is a one-commit revert with no database migrations or protocol changes.

## Open Questions

None — all decisions are resolved above.
