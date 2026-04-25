## Why

Tickets #3–#6 landed L1 (AX-tree), L2 (DOM heuristics), L3 (semantic rerank), and L4 (vision fallback) of `agent/locate.py`. Every successful resolution today re-runs the full tier ladder from scratch, which is fine for a one-shot test but wrong for the agent loop: the same `(origin, intent)` pair is going to be resolved many times across a single task and across tasks targeting the same site, and the expensive tiers (L3 = LLM rerank, L4 = vision LLM) compound that cost. The plan is explicit about this — `task2/plan.md` lines 44, 70, 138, 141–142, 236, and TDD ticket #7 (line 247) all describe a `(origin, intent) → ax_fingerprint` SQLite cache that future runs hit first and that invalidates on AX-fingerprint drift. Ticket #7 makes good on that contract.

The cache is also the lever the spec calls **self-maintenance**: a stored selector + AX-fingerprint that revalidates cheaply on every read, falls through to the live tier ladder when the page has drifted, and refreshes itself in place. Without it, "self-maintaining locator" is just rhetoric.

## What Changes

- Add a new module `task2/agent/locator_cache.py` exposing `LocatorCache` — a thin SQLite-backed key/value store keyed by `(origin, intent)` with a single-table schema (one row per entry, columns spelled out in `design.md`). Constructor takes an explicit `path` (defaulting to `:memory:` for tests; production callers pass a file path, typically resolved from the `LOCATOR_CACHE_PATH` environment variable in the agent loop wiring of a later ticket). No global singleton, no module-level side effects.
- Add a new locator tier value `"cache"` to `LocateResult.tier`. Update the (informal) tier set in `agent/locate.py` to include `"cache"` as a peer of `"L1_ax" | "L2_dom" | "L3_rerank" | "L4_vision"`. The existing tier values are unchanged.
- Extend `agent.locate.locate(page, intent, *, llm_chat=None, cache=None) -> LocateResult` so that:
  - On entry, if a non-`None` cache is passed, derive `origin` from `page.url` (scheme + host + port), look up `(origin, intent)`. If a row exists, recompute the AX fingerprint of whatever element the cached `selector` currently resolves to (or, for an L4 entry, the fingerprint of the saved coords + intent), and compare against the cached `ax_fingerprint`. On match, return a `LocateResult` with `tier="cache"`, the cached `selector` / `coords`, the cached `role` / `name`, the cached `ax_fingerprint`, and the cached `confidence` — no L1–L4 work is done, no LLM call is made.
  - On AX-fingerprint mismatch (drift) OR on cached selector resolving to zero elements (element removed), delete the row and fall through to the existing L1–L4 ladder. The fall-through path is unchanged.
  - After a successful non-cache resolve, write/replace the row with the freshly resolved `(role, name, selector, ax_fingerprint, confidence, tier, coords?)` plus a UTC ISO-8601 timestamp.
- Cache scoping: the key is exactly `(origin, intent)`. Different origins (different scheme/host/port) MUST NOT share entries. Different intents on the same origin MUST NOT share entries.
- L4 cache entries are explicitly **out of scope for ticket #7's revalidation logic**. The AX-fingerprint revalidation rule (re-resolve the selector and recompute the fingerprint) requires a DOM selector; L4 entries store coordinates instead. Ticket #7 SHALL still write L4 entries to the cache so the persistence side is exercised, but on read SHALL treat every L4 entry as a forced miss + invalidate (the cache row is deleted and the tier ladder runs again). A future ticket can introduce a vision-revalidation strategy once the eval set actually surfaces "L4 cache hit at the right cost." Justified in `design.md`.
- Tests live in `task2/tests/agent/test_locator_cache.py`. The cache uses a real in-memory SQLite (`:memory:`) — per repo CLAUDE.md, mock the network, not the contract. The agent.llm chat callable is mocked via the existing `_make_chat_stub` helpers, including `fail_if_called=True` for cache-hit assertions ("LLM SHALL NOT be invoked").

Out of scope: wiring the cache into the agent loop / browser tool surface (that is part of the loop ticket); a compaction/eviction policy beyond "replace-on-write"; multi-process locking; an admin endpoint to inspect/clear the cache. The plan calls a cold cache acceptable, so we do not need persistence guarantees beyond "write commits, next read sees the row."

## Capabilities

### New Capabilities

- `locator-cache`: SQLite-backed `(origin, intent) → (selector, ax_fingerprint, tier, role, name, confidence, coords?, ts)` cache with explicit-path construction, AX-fingerprint revalidation on read, invalidate-on-drift, write-on-resolve, scoping by origin and by intent, and explicit L4-entry forced-miss policy.

### Modified Capabilities

- `locator-pipeline`: extend the entry point and the `LocateResult` shape:
  - `locate()` gains an optional `cache: LocatorCache | None = None` keyword parameter. When `None`, behaviour is unchanged from ticket #6; when set, the cache-probe / cache-write semantics described above apply.
  - The `LocateResult.tier` set is extended with `"cache"`. All other `LocateResult` fields keep their meaning; on a cache hit the values are populated from the stored row, including a non-empty `ax_fingerprint` and the original tier's `confidence`.

## Impact

- **Code**: new `task2/agent/locator_cache.py`; modified `task2/agent/locate.py` (extend `locate()` signature, add `"cache"` tier value, route through `LocatorCache.get` / `LocatorCache.put` / `LocatorCache.invalidate`); new `task2/tests/agent/test_locator_cache.py`; possibly a small fixture pair (an HTML page where the same intent resolves on a first load, then a mutated copy where the AX-fingerprint changes — alternatively, both states are produced by JS mutation on a single fixture, decided in `design.md`).
- **Dependencies**: none new. SQLite ships with Python's stdlib (`sqlite3`).
- **Existing modules**: `agent/llm.py` unchanged. `agent/browser.py` unchanged. L1–L4 implementations unchanged — only `locate()` is touched.
- **Schema migration**: not applicable. The cache file is created fresh on first construction; a missing file is not an error. Per the plan's "cold cache is acceptable" rule, dropping the file is the migration path.
- **Deployment**: opens up the `LOCATOR_CACHE_PATH` env var as the production cache location. The deploy ticket (#18) will mount a Zeabur volume there; falling back to `:memory:` (cold cache) is acceptable when no path is configured.
- **Tracing**: prepares the ground for the `LocateEvent.cache_action` field listed in `task2/plan.md` line 142 — `"read"` on hits, `"write"` on writes, `"invalidate"` on drift / removed-element. The trace writer itself lands in ticket #12; this ticket only ensures the cache emits these signals through its return values / the `tier` field.
