## Why

`observe._ax_nodes` calls `page.context.new_cdp_session(page)` and `cdp.detach()` on every single `build_observation` invocation — once per agent step. Opening and tearing down a CDP session is a synchronous round-trip that adds latency to every observation and produces unnecessary churn (allocation, protocol handshake, teardown) N times where N is the number of steps in a run. The session should be opened once per page lifetime and reused.

## What Changes

- `Browser` gains a `_cdp_sessions: dict[str, CDPSession]` instance attribute (keyed by page identity) initialized to `{}` in `__init__`.
- `_ax_nodes` in `observe.py` accepts a `Browser` instance (or a compatible duck-type) and retrieves or lazily creates a cached CDP session from it instead of calling `new_cdp_session` on every call.
- `Browser.__exit__` iterates all cached sessions and calls `detach()` on each, swallowing individual errors so teardown of the browser context still proceeds.
- Page navigation that produces a new page object (new `_page` identity) is treated as a cache miss; a fresh session is opened for the new page and cached under its identity key.
- `build_observation` passes the `Browser` instance to `_ax_nodes` (signature change, not a public API change — `_ax_nodes` is private).

## Capabilities

### New Capabilities
- `cdp-session-cache`: `Browser` caches CDP sessions by page identity and reuses them across `build_observation` calls; detaches all sessions on `__exit__`.

### Modified Capabilities
- `ax-tree-observation`: The `_ax_nodes` call site changes from per-call attach/detach to cached-session lookup; the observable behavior of `build_observation` (returned dict shape, AX tree content, fingerprint semantics) is unchanged.

## Impact

- `task2/agent/browser.py` — adds `_cdp_sessions` dict attribute and `__exit__` cleanup loop.
- `task2/agent/observe.py` — `_ax_nodes` signature changes to accept a `Browser`-like object; session acquisition moves from per-call to cached.
- `task2/tests/agent/test_observe.py` — existing tests must continue to pass unchanged; three new test functions added for the cache behaviors.
- No changes to public API surface, trace schema, eval cases, or any other module.
