## Context

`task2/agent/locate.py` after ticket #6 has the full L1–L4 ladder. Every call to `locate(page, intent)` re-runs the ladder from scratch: an AX-tree query for L1, possibly a DOM heuristic pass for L2, possibly an LLM round-trip for L3, possibly a screenshot + vision LLM round-trip for L4. The plan calls explicitly for an `(origin, intent) → ax_fingerprint` SQLite cache (`task2/plan.md` line 44, 70) so future runs hit the cache first and only fall through on AX-fingerprint mismatch (drift).

The ticket text on line 247 is one line: "second resolve of same intent hits cache; AX-fingerprint mismatch invalidates." Everything else — schema layout, how to revalidate L4 entries, where the cache file lives — is design. This document settles those.

Constraints inherited from the repo:

- **TDD non-negotiable.** Tests exist before code. Tests use a real SQLite (in-memory `:memory:` is fine); CLAUDE.md is explicit that we mock the network, not the contract — and the cache *is* the contract. Mocking SQLite would test wrappers, not the cache.
- **`uv` + `ruff` only.** No `pip`, no `black`, no `pre-commit` hook bypass. Lint must be clean.
- **No hardcoded LLM provider.** Already true of `agent/llm.py`; the cache itself does not call the LLM, but ticket #7 must not introduce a path that does.
- **No abstractions for hypothetical second callers.** The only caller of the cache today is `agent.locate.locate()`. The cache module SHOULD NOT ship a "pluggable backend" interface, a "cache factory," or a generic key/value protocol. One class, one SQLite file, one set of methods.
- **Backwards-compatible signature.** `locate(page, intent)` and `locate(page, intent, llm_chat=...)` continue to work after this change. The new `cache=` parameter is keyword-only and defaults to `None`. When `None`, behaviour is exactly what ticket #6 shipped.

Driver scenarios from the proposal:

1. First resolve writes a row; second resolve against the same DOM hits and skips the LLM stub entirely.
2. Page mutates (the cached selector now resolves to an element with a different accessible name) → cache invalidates, ladder runs again, cache row is replaced.
3. Cached selector no longer resolves to anything → cache invalidates, ladder runs again.
4. Same intent, different origin: independent rows.
5. Same origin, different intent: independent rows.
6. L4 (vision) entries: written but always forced-miss on read.

## Goals / Non-Goals

**Goals:**

- A `LocatorCache` class in a new `task2/agent/locator_cache.py` module exposing exactly the surface `locate()` needs:
  - `__init__(self, *, path: str = ":memory:")` — open / create the SQLite file at `path`. Default `:memory:` so tests do not have to manage temp files. `path` is an explicit kwarg; resolution from `LOCATOR_CACHE_PATH` env var is the *caller's* job (the agent loop ticket), not the cache module's. This keeps the cache import-side-effect-free and TDD-friendly.
  - `get(self, *, origin: str, intent: str) -> CacheEntry | None` — exact-match read.
  - `put(self, entry: CacheEntry) -> None` — INSERT OR REPLACE.
  - `invalidate(self, *, origin: str, intent: str) -> None` — DELETE.
  - `close(self) -> None` — close the underlying connection. Idempotent.
  - Context-manager protocol (`__enter__` / `__exit__`) so callers can use `with LocatorCache(path=...) as cache:` if they want, but plain construction also works.
- A frozen `CacheEntry` dataclass with the columns spelled out below.
- A single SQLite table `locator_cache` with the columns spelled out below. No schema migrations — we drop the table on first construction if its column set does not match the current definition (cold cache is acceptable per plan.md line 236).
- Cache integration in `agent.locate.locate()`:
  - New keyword-only parameter `cache: LocatorCache | None = None`.
  - On entry, if `cache is not None`, derive `origin = _origin_from_url(page.url)` (scheme + lower-cased host + explicit port; default ports 80/443 are normalised), call `cache.get(origin=origin, intent=intent)`.
  - If a row exists and the row's `tier` is one of `{"L1_ax", "L2_dom", "L3_rerank"}`: re-resolve `row.selector` via `page.locator(row.selector)`. If `count() == 0`, treat as drift → `cache.invalidate(...)` and fall through. If `count() >= 1`, recompute the AX fingerprint of `locator.first` using the same fingerprinting rule as the row's `tier` produced (see "Fingerprint revalidation per tier" below). Compare with `row.ax_fingerprint`. Equal → return a `LocateResult(tier="cache", ...)` populated from the row. Different → `cache.invalidate(...)` and fall through.
  - If a row exists and the row's `tier` is `"L4_vision"`: forced miss. `cache.invalidate(...)` and fall through. (See L4 decision below.)
  - On a successful resolve from any L1–L4 tier when `cache is not None`, call `cache.put(...)` with the freshly resolved `LocateResult`'s fields. The cache write happens before returning so callers see a consistent post-condition.
- A new `LocateResult.tier` value `"cache"`. We do NOT promote it to a `Literal[...]` type hint yet (the existing tier field is a plain `str` per ticket #6); we just permit the new value in code paths that route through the cache.
- Tests in `task2/tests/agent/test_locator_cache.py` covering: cold-cache write, warm-cache hit (LLM stub asserts not-called), AX-fingerprint mismatch invalidation (page mutates between calls), removed-element invalidation, origin scoping, intent scoping, L4 entries forced-miss, configurable path.
- Lint clean (`uv run ruff check .`, `uv run ruff format .`).

**Non-Goals:**

- Wiring the cache into `agent/browser.py` or the agent loop. `browser.py` is still selector-based; the loop does not exist yet (ticket #9). When the loop lands it will own the responsibility of constructing one `LocatorCache(path=os.environ.get("LOCATOR_CACHE_PATH", ":memory:"))` per process and threading it through.
- TTL / size-based eviction. The cache is replace-on-write only. Eviction lands the day the eval set surfaces it as a real failure mode.
- Multi-process locking. Python's `sqlite3` connection is single-process by default; the agent runs one task per request per worker (plan line 235), so this is fine. If we ever fork workers that share a cache file, ticket #18 (Dockerfile + Zeabur) is the right place to revisit.
- Cross-tier promotion ("the cache stored an L3 hit; on the next resolve, try L1 anyway in case the page got cleaner"). Out of scope. The cache returns the cached tier verbatim as `tier="cache"`.
- A trace `LocateEvent` writer. The plan's `cache_action` field (line 142) is part of the trace schema (ticket #12). This ticket only ensures `locate()` produces enough information for that future writer to fill the field — namely, the new `"cache"` tier value and the cache-internal `get`/`put`/`invalidate` calls — without itself emitting events.
- Validating that the *cached selector* still references the *same DOM node identity*. We validate by AX fingerprint, which is a content equivalence, not an identity check. That is the point — if the page re-renders but exposes the same accessible affordance, the cache hits.
- Vision-revalidation for L4 cache entries (see decision below).
- Hardcoding the cache path in production. The agent loop ticket will read `LOCATOR_CACHE_PATH`; this ticket is path-agnostic.
- Surfacing cache statistics via an HTTP endpoint or admin tool.

## Decisions

### Storage: one SQLite table, fixed schema, drop-on-mismatch

```sql
CREATE TABLE IF NOT EXISTS locator_cache (
    origin            TEXT NOT NULL,
    intent            TEXT NOT NULL,
    role              TEXT NOT NULL,
    name              TEXT,                 -- nullable: bare-role queries (e.g. "heading")
    selector          TEXT NOT NULL,        -- empty string for L4_vision rows
    ax_fingerprint    TEXT NOT NULL,
    confidence        REAL NOT NULL,
    tier              TEXT NOT NULL,        -- "L1_ax" | "L2_dom" | "L3_rerank" | "L4_vision"
    coords_x          INTEGER,              -- nullable; populated for L4_vision
    coords_y          INTEGER,              -- nullable; populated for L4_vision
    written_at_utc    TEXT NOT NULL,        -- ISO-8601 'YYYY-MM-DDTHH:MM:SSZ'
    PRIMARY KEY (origin, intent)
);
```

- **`PRIMARY KEY (origin, intent)`** enforces the cache contract. `INSERT OR REPLACE` semantics on `put`.
- **`tier` is stored verbatim from the resolving call.** The cache returns it through `CacheEntry.tier`; on read the `LocateResult.tier` is *overridden* to `"cache"` so callers can distinguish a cache hit from a fresh resolve at the same tier.
- **No `ROWID` / surrogate `id`.** The two-column primary key is the only way to look up a row in this scheme.
- **No indexes beyond the implicit primary-key index.** The only access pattern is `WHERE origin = ? AND intent = ?`, which uses the PK directly.
- **Schema mismatch on construction → drop + recreate.** On `__init__`, query `PRAGMA table_info(locator_cache)`; if the column list does not match the expected set exactly, `DROP TABLE locator_cache` and recreate. This is the "cold cache is acceptable" rule operationalised. We do not write a migration framework for a single-table cache.

Alternative considered: a JSON blob column instead of typed columns. Rejected — typed columns let the test suite assert specific values (e.g. `coords_x IS NULL` for non-L4 rows) without parsing JSON, and the column count is small.

Alternative considered: separate tables per tier. Rejected — the read path needs one query per `(origin, intent)`, not one per tier; a union view would be needless ceremony.

### Cache key: `(origin, intent)` where `origin = scheme + "://" + host + (":" + port if non-default)`

- `origin` is derived from `page.url` via `urllib.parse.urlsplit`.
- `scheme` is lower-cased.
- `host` is lower-cased.
- `port`: if explicit, included as `:{port}`. If absent and scheme is `http`, treat as `:80`; if absent and scheme is `https`, treat as `:443`. Then strip the `:80`/`:443` suffix unconditionally so the canonical form for `http://example.com/` is `http://example.com` (no port suffix). Non-default ports are always retained — `http://example.com:8080/` → `http://example.com:8080`. Schemes other than `http`/`https` (e.g. `file://` for local fixtures served via `http.server`, `data:` for synthetic pages) keep whatever port the URL carries; for `file://` we use the empty host as-is.
- `intent` is the verbatim string passed to `locate()` — no lower-casing, no whitespace collapsing. Two different phrasings of the same intent are different cache keys, because they will (in general) be sent to different LLM calls and may resolve differently. The plan's `(origin, intent) → ax_fingerprint` contract is exactly this.

Alternative considered: also key on `(role, name)` derived from `parse_intent`. Rejected — the parsed pair is a function of `intent`, so it is redundant in the key. We do store `role` and `name` in the row for debugging.

Alternative considered: hash the intent. Rejected — opaque keys make eyeballing the SQLite file (during eval debugging) painful, and the storage savings are negligible (one cache row per intent string, ten or twenty per task).

The local-fixture test suite uses `http://127.0.0.1:<random>` URLs, which produce distinct origins per port. That is exactly the scoping property we want to test against.

### `LocateResult.tier == "cache"` as a peer of L1–L4

A cache hit produces:

```python
LocateResult(
    tier="cache",
    role=row.role,
    name=row.name,
    selector=row.selector,
    ax_fingerprint=row.ax_fingerprint,
    confidence=row.confidence,
    coords=(row.coords_x, row.coords_y) if row.coords_x is not None else None,
)
```

We override `tier` to `"cache"` and keep the original `confidence` from the stored row. Callers (and the future trace writer in ticket #12) can tell a cache hit from a fresh resolve at the same tier by inspecting `tier` alone.

Alternative considered: keep the stored `tier` and add a separate `from_cache: bool` field. Rejected — the plan's `LocateEvent.tier` enum (line 138) already includes `"cache"` as a discriminator; mirroring that in `LocateResult.tier` keeps one source of truth across the trace and the resolver.

Alternative considered: tie `confidence` to the cache itself (e.g. `0.9` for a cache hit). Rejected — the cache does not improve the resolution; it only avoids redoing it. The original tier's confidence is the right number.

### Fingerprint revalidation per tier

To revalidate a cached row on read, we need to reproduce the exact fingerprint formula the original tier used:

- **L1_ax**: `sha256(f"{role}:{accessible_name_of_first_match}".encode()).hexdigest()`. We re-resolve the cached selector, take `.first`, run the existing `_ACCESSIBLE_NAME_JS` against it, and recompute. Match → hit.
- **L2_dom**: `sha256(f"{role}:{name}:{strategy}".encode()).hexdigest()`. The `strategy` was baked into the original row's fingerprint; we cannot recover it from page state alone. Decision: we re-resolve the cached `selector` and check `count() == 1`. If yes, we recompute the L2 fingerprint as `sha256(f"{role}:{name}:{stored_strategy}".encode())` where `stored_strategy` is *not* in the schema. To avoid an extra column, we instead compare the stored fingerprint directly against the *stored* fingerprint of the cached row, and use the L1 fingerprint of `locator.first` as a tie-breaker — if the L1 fingerprint of the re-resolved element is also the same as it was when L2 wrote the row, we hit. To make this concrete, on `put` for an L2 row we *also* compute and store the AX-name of `locator.first` as part of the fingerprint inputs:

  Updated rule: every cached row's fingerprint, regardless of source tier, is recomputed at the cache layer from the *currently re-resolved* element's `(role, accessible_name)` pair using the same `sha256(f"{role}:{accessible_name}".encode())` recipe as L1. This is the **canonical revalidation fingerprint**. The original tier's fingerprint is stored separately as `ax_fingerprint`; the canonical fingerprint is what we compare on read.

  In practice this means `ax_fingerprint` in the schema is the canonical revalidation fingerprint (L1-style, computed at write time over the currently-resolved element), not the tier-specific one the original `LocateResult` carried. The original tier's selector and tier label are still stored (so a cache hit returns the same `selector` and `tier`-on-`LocateResult`-via-`"cache"`), but the fingerprint we compare is uniform.

  This means a cache row's fingerprint is **always** the L1-style fingerprint of the element the selector currently resolves to. On read we just recompute the same thing and compare. No tier-specific revalidation logic.

- **L3_rerank**: same canonical rule. The cached selector (`role=...[name=...] >> nth=N`) re-resolves to an element; we compute its L1-style AX fingerprint and compare.
- **L4_vision**: stored selector is empty; the cached fingerprint cannot be re-derived from page state without a vision call. Forced miss on read (see next decision).

So the actual schema change vs. what L1/L2/L3 currently produce: the row's `ax_fingerprint` column stores the *L1-style fingerprint of the element the selector points to at write time*, NOT the tier's own fingerprint formula. The `LocateResult.ax_fingerprint` returned to the caller (in the cache hit) is this same canonical value, not the value the original tier originally returned in its uncached `LocateResult`. We accept this mismatch: callers do not depend on the tier-specific fingerprint formula being preserved across a cache round-trip. The plan only contracts on fingerprint *equality across runs that pick the same element*, and the canonical L1-style fingerprint satisfies that.

Alternative considered: store the tier-specific fingerprint and write a per-tier revalidation function. Rejected — adds three (then four, when L5 lands) revalidation paths for no observable benefit. The canonical-fingerprint rule is the simplest contract that satisfies the plan's "fingerprint matches → hit, mismatches → invalidate" rule.

Alternative considered: hash the candidate's full AX subtree (role + name + children's roles/names). Rejected — too brittle; harmless DOM additions inside a button (e.g. an icon span) would invalidate the cache on every render. The role-and-name pair is the right granularity for "is this still the same affordance?".

### L4 entries: written but forced-miss on read

L4 rows have `selector = ""` and a fingerprint derived from `vision:{intent}:{cx}:{cy}` at write time (per `agent/locate.py` `locate_l4`). To revalidate without re-running the vision LLM we would need either:

1. Take a fresh screenshot, re-extract the same coords, recompute the fingerprint. This is a vision LLM call — exactly the cost the cache is supposed to avoid. Net-negative.
2. Trust the coords blindly and click without revalidating. Unsafe — pages can mutate, coords can now point to a different element, and we have no AX signal to detect that.
3. Keep a screenshot hash and compare with a fresh screenshot byte-for-byte. False negatives on every animation frame.

None of these is worth implementing in ticket #7. Decision: **L4 cache entries are written for completeness (so the persistence side of the cache is exercised against every tier) but every L4 row is treated as a forced miss on read and immediately invalidated.** This is documented behaviour, not a bug.

A future ticket can introduce a fourth revalidation path (e.g. "if the L1 AX fingerprint at the cached coords matches what it was when the row was written, hit") once the eval set actually surfaces "L4 cache hit at the right cost" as a real win. The plan's only contract on caching is at the AX-tier level (`(origin, intent) → ax_fingerprint`), so this is a defensible scope boundary.

Alternative considered: skip L4 writes entirely. Rejected — exercising the write path against every tier is cheap, and a future ticket that does enable L4 revalidation will appreciate the rows already being there.

Alternative considered: scope the ticket to "AX-tier cache only, L4 not stored." Rejected — the schema needs `coords_x`/`coords_y` columns anyway for the day L4 revalidation lands; introducing them now is one schema decision settled, not deferred.

### Configurable path: explicit kwarg, no env var resolution in the cache module

```python
class LocatorCache:
    def __init__(self, *, path: str = ":memory:"):
        self._conn = sqlite3.connect(path)
        ...
```

- **Default `:memory:`**, so tests can construct `LocatorCache()` without temp files.
- **Production callers (the agent loop, ticket #9) read `LOCATOR_CACHE_PATH` themselves** and pass it in. The cache module does not import `os`.

Reason: keeping the module import-side-effect-free is the TDD-friendly choice. A test that imports `agent.locator_cache` should not silently open a file on disk because `LOCATOR_CACHE_PATH` happens to be set in CI. This mirrors `agent/llm.py`'s pattern where `LLM_BASE_URL` is read by the function, not at module load.

Alternative considered: a class-level factory `LocatorCache.from_env()`. Rejected — premature; ticket #9 will call `os.environ.get(...)` once, in one place, and pass the result to the constructor. That is one line of code, not worth a method.

Alternative considered: positional `path` argument. Rejected — keyword-only protects against future arguments shifting position.

### Cache integration in `locate()`: probe-then-resolve, write-on-success

```python
def locate(page, intent, *, llm_chat=None, cache=None):
    role, name = parse_intent(intent)

    if cache is not None:
        origin = _origin_from_url(page.url)
        row = cache.get(origin=origin, intent=intent)
        if row is not None:
            hit = _try_cache_hit(page, row)
            if hit is not None:
                return hit
            cache.invalidate(origin=origin, intent=intent)

    result = _resolve_via_ladder(page, role=role, name=name, intent=intent, llm_chat=llm_chat)

    if cache is not None:
        cache.put(_entry_from_result(origin, intent, result, page))

    return result
```

Where:

- `_try_cache_hit` returns a `LocateResult(tier="cache", ...)` on success and `None` on any failure (zero matches, fingerprint mismatch, L4 row).
- `_resolve_via_ladder` is the existing L1 → L2/L3/L4 cascade, factored out for readability — no behaviour change.
- `_entry_from_result` recomputes the canonical L1-style AX fingerprint over the resolved element. For L4 results it reuses the L4 vision fingerprint as a placeholder; on read those rows will be forced-missed anyway.
- The `origin` computation happens once on entry and is reused for both probe and write to keep the two keys identical.

Alternative considered: write the cache entry inside each L1/L2/L3/L4 function. Rejected — spreads the cache write across four locations and tightly couples each tier to the cache module. One write site at the orchestrator is cleaner.

Alternative considered: probe the cache *only* when the URL has an HTTP/HTTPS scheme. Rejected — the file:// and data:// schemes are real test surfaces (the local fixture server uses http://127.0.0.1; data:// is used by L4 vision tests). Skipping the cache for them would create a "cache works in tests, doesn't work in production" inconsistency. Better to cache uniformly.

### Fixture strategy: one fixture page + a JS mutator for drift

The drift-invalidation test needs a page where the *same* `(origin, intent)` resolves on first call, then resolves to a different AX-fingerprint on a second call. Two implementation paths:

1. **Two static HTML files** (e.g. `cache_drift_v1.html` and `cache_drift_v2.html`) served on the *same* origin by remapping the path. Hard to do with the existing `fixture_server`, which serves files by literal path.
2. **One HTML file + a JS hook** the test triggers via `page.evaluate("...")` between the two `locate()` calls. The first call sees the original DOM; the test mutates the DOM (e.g. changes a button's text); the second call sees the mutated DOM. The cache row's fingerprint no longer matches the re-resolved element's fingerprint, so the cache invalidates.

We pick option 2. The fixture file `task2/tests/fixtures/cache_drift.html` exposes a Submit button with `id="target"` and a `<script>` defining `window.__rename = (newName) => document.getElementById('target').textContent = newName;`. The test calls `page.evaluate("__rename('Send')")` between the two `locate()` calls.

For "cached element removed" tests, the same fixture exposes `window.__remove = () => document.getElementById('target').remove();`.

For origin-scoping tests, the existing `fixture_server` already serves on a random port. The "different origin" case is exercised by spinning up a *second* `fixture_server` (on a different random port) within the test — `conftest.py` already provides the helper as a function-scoped fixture that can be requested twice in the same test, OR we add a session-scoped factory if needed. Simpler alternative: use a single fixture-server URL with two distinct paths whose origins are equal — this would NOT distinguish origins. So the test must use two ports. Verify what `conftest.py` actually offers when implementing.

Alternative considered: hosts file / `localhost` aliasing for two different origins on the same port. Rejected — too brittle, requires test-environment setup outside the test code.

### `CacheEntry` dataclass mirrors the row exactly

```python
@dataclass(frozen=True)
class CacheEntry:
    origin: str
    intent: str
    role: str
    name: str | None
    selector: str
    ax_fingerprint: str
    confidence: float
    tier: str               # "L1_ax" | "L2_dom" | "L3_rerank" | "L4_vision"
    coords: tuple[int, int] | None
    written_at_utc: str
```

`written_at_utc` uses `datetime.now(UTC).isoformat(timespec="seconds")` — NOT a SQL `CURRENT_TIMESTAMP` default, because we want to control the timestamp from Python (testable, and avoids subtleties with SQLite's local-time defaults).

Frozen so callers cannot mutate cache state by accident (we hand the same dataclass back from `get` and accept it in `put`).

### Module load semantics

`agent.locator_cache` imports `sqlite3` and `dataclasses` at module level (both stdlib, no cost). It does NOT import `agent.llm`, `agent.locate`, or `playwright`. `agent.locate` imports `LocatorCache` lazily inside the `locate()` function body, the same way it imports `agent.llm.chat` lazily today, so existing tests that exercise L1/L2 only (without ever touching the cache) do not pay any SQLite import cost.

Alternative considered: top-level import of `LocatorCache` in `agent/locate.py`. Rejected — same import-cost / TDD-cleanliness argument used for `agent.llm` lazy import.

### Tests live alongside existing locator tests

`task2/tests/agent/test_locator_cache.py`. Reuses the existing `fixture_server`, `playwright_chromium` pytest fixtures, the existing `_make_chat_stub` helper (or a copy if the helper is private to `test_locate_l3.py` — implementer decides). Reuses real SQLite with `LocatorCache(path=":memory:")` per test. No DB mocking.

A test that asserts "the LLM SHALL NOT be invoked on a warm cache hit" uses the `fail_if_called_stub` pattern from ticket #5. A test that asserts "the cache stores the right values" does so by reading the SQLite row directly via the cache's `get` method (since the cache is the system under test, querying it is fair game; we do not also dig into the underlying connection from the test).

## Risks / Trade-offs

- **Canonical fingerprint mismatch with the original tier's fingerprint formula.** A cache hit returns an `ax_fingerprint` that is the L1-style fingerprint of the resolved element, NOT the tier-specific fingerprint the original `locate_lN` returned. → Documented behaviour. Trace replay (ticket #12) records the cache hit as a `LocateEvent` with `tier="cache"` and the canonical fingerprint; downstream consumers do not need to reconstruct the tier-specific value from a cached row. The risk is purely that someone writes a test asserting `cached_result.ax_fingerprint == fresh_l3_result.ax_fingerprint`, which would fail. We document this in the spec scenario for cache hits.

- **Cache hit on a moved-but-still-same-name element.** If the page reorders sections so "Save in Settings" is now where "Save in Profile" used to be, but both buttons still have role=button + name="Save", an L1-style fingerprint will tie them and the cache will hit on the wrong one. → This is a known trade-off of "fingerprint by content equivalence, not identity." The L3 tier exists precisely to disambiguate by section heading; if the user task originally went through L3 and the cache returns "the first matching role+name element," it can pick wrong. → Mitigation: for L3 rows specifically, the canonical fingerprint computed at write time is over `locator.first` of the cached `>> nth=N` selector — so if `nth=N` has shifted to a different section, the canonical fingerprint at write time was over a different element, and we *would* notice on a second read. The risk is concentrated in L1 rows where role+name was originally unique and is still unique but now points to a different element (e.g. a navigation bar swap). → We accept this; the agent loop's act-then-observe diff (plan line 61) catches "click had no effect" and re-routes.

- **L4 forced-miss is a known inefficiency.** Every L4 row written is read once, invalidated, and rewritten. → Documented. Net cost: one extra DB DELETE per L4 resolve. Negligible.

- **SQLite single-connection per process.** `sqlite3.connect(...)` returns a connection bound to one thread by default. The agent runs synchronously per request and does not currently spawn worker threads inside a request, so this is fine. → If a future ticket goes async, we revisit by enabling `check_same_thread=False` and adding a connection pool. Not needed today.

- **`:memory:` cache is per-process.** The tests construct one cache per test, so no cross-test pollution. In production with `:memory:` (no env var set), the cache resets every process restart — exactly the "cold cache" outcome the plan accepts. → No mitigation needed.

- **Schema drop-on-mismatch loses data on upgrade.** The day we add a column, every existing cache file is wiped. → Acceptable per plan ("cold cache is acceptable"). If a future ticket needs additive schema changes without data loss, it can introduce a `schema_version` table and a real migration. Not today.

- **`origin` derivation skipped for unusual URL schemes.** `data:` URIs have no host; we fall back to a stable canonical form (e.g. `data:`). The test surface is small enough that "every test uses http://127.0.0.1:port" is the realistic case. → Edge cases are documented; the spec does not require correctness on `chrome-extension://` etc.

- **Concurrent writes from two processes pointing at the same file.** SQLite serialises via WAL or journal; on a Zeabur deploy with one worker per container this is fine. → If the deploy ever scales horizontally beyond one worker per file, the cache file becomes a contention point. The plan's "single browser per request" cap (line 235) makes this the right scope today.

- **Tests now use real SQLite, increasing per-test setup cost slightly.** `:memory:` SQLite construction is sub-millisecond; the test suite gains maybe 50ms total. → Trivial.

- **Backwards compatibility on `locate()` call sites.** Adding `cache=None` keyword-only is backwards-compatible. The L1/L2/L3/L4 tier functions are unchanged. → No mitigation needed.
