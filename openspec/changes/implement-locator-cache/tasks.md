## 1. Test fixtures (red prep)

- [ ] 1.1 Create `task2/tests/fixtures/cache_drift.html` containing a single `<button id="target">Submit</button>` with role=button + accessible name "Submit", and a `<script>` that exposes `window.__rename = (newName) => { document.getElementById('target').textContent = newName; }` and `window.__remove = () => { document.getElementById('target').remove(); }` and `window.__add = (text) => { const b = document.createElement('button'); b.textContent = text; document.body.appendChild(b); }`. No other element in the page may have role=button.
- [ ] 1.2 Confirm the existing `fixture_server` and `playwright_chromium` pytest fixtures in `task2/tests/conftest.py` allow constructing TWO independent fixture servers within a single test (different ports → different origins). If they do not, add a session-scoped or function-scoped factory fixture (`fixture_server_factory`) that yields a callable returning a fresh server URL on each invocation, and document the addition. Do NOT change the default `fixture_server` fixture's signature — additive only.
- [ ] 1.3 No new HTML files for the L4-cache test. The existing `locate_l4.html` fixture (already present after ticket #6) is reused for the L4-forced-miss scenario.

## 2. Failing tests (red) — `LocatorCache` unit tests

- [ ] 2.1 Add `task2/tests/agent/test_locator_cache.py`. Import `LocatorCache, CacheEntry` from `agent.locator_cache` so the import alone fails until the module exists.
- [ ] 2.2 Write `test_construct_in_memory_default` — `cache = LocatorCache()`; assert it is constructed without error and the underlying SQLite reports an in-memory database (e.g. inspect `cache._conn` and check the `database` PRAGMA, OR insert a row and confirm a second construction with no path argument does NOT see that row).
- [ ] 2.3 Write `test_construct_with_file_path` (using pytest's `tmp_path`) — construct against `tmp_path / "locator.sqlite"`; assert the file exists; insert a row; close; reconstruct against the same path; assert the row is still present.
- [ ] 2.4 Write `test_schema_mismatch_drops_and_recreates` — open the SQLite file directly with `sqlite3.connect(...)`, create a `locator_cache` table with a deliberately wrong column set (e.g. just `origin TEXT, intent TEXT`), insert a row, close. Then construct `LocatorCache(path=...)` and assert the row is gone and the new schema is in place (verify by `PRAGMA table_info(locator_cache)`).
- [ ] 2.5 Write `test_constructor_ignores_locator_cache_path_env_var` — set `LOCATOR_CACHE_PATH` via `monkeypatch.setenv` to `tmp_path / "should_not_be_used.sqlite"`; construct `LocatorCache()` with no arguments; insert a row; close; assert the file at `LOCATOR_CACHE_PATH` does NOT exist (the constructor MUST NOT have read the env var).
- [ ] 2.6 Write `test_get_on_empty_cache_returns_none` — fresh cache; `cache.get(origin="http://x", intent="Save button")` returns `None`.
- [ ] 2.7 Write `test_put_then_get_round_trips` — construct a `CacheEntry` with all fields; `cache.put(entry)`; assert `cache.get(...)` returns an equal `CacheEntry` (by `==`).
- [ ] 2.8 Write `test_put_replaces_existing_row` — insert `entry_v1`; insert `entry_v2` with the same `(origin, intent)` but a different `selector` and `ax_fingerprint`; assert `cache.get(...)` returns `entry_v2`; assert exactly one row exists for that key (count via a direct `cache._conn.execute("SELECT COUNT(*) FROM locator_cache")` since the cache is the system under test, not a side dependency).
- [ ] 2.9 Write `test_invalidate_deletes_row` — insert a row; `cache.invalidate(origin=..., intent=...)`; assert `cache.get(...)` returns `None`.
- [ ] 2.10 Write `test_invalidate_missing_row_is_noop` — fresh cache; call `invalidate(...)` for a non-existent key; assert it does not raise.
- [ ] 2.11 Write `test_cache_scoped_by_origin` — insert one entry at `(origin="http://a", intent="x")`; assert `get(origin="http://b", intent="x")` returns `None`.
- [ ] 2.12 Write `test_cache_scoped_by_intent` — insert one entry at `(origin="http://x", intent="a")`; assert `get(origin="http://x", intent="b")` returns `None`.
- [ ] 2.13 Write `test_cache_entry_is_frozen` — try to mutate a returned `CacheEntry`'s field; assert `dataclasses.FrozenInstanceError` is raised.
- [ ] 2.14 Write `test_close_is_idempotent` — `cache.close(); cache.close()`; second call does not raise.
- [ ] 2.15 Write `test_context_manager` — `with LocatorCache(path=":memory:") as c: c.put(...)`; outside the `with`, `c.get(...)` raises (or returns `None`, depending on the close-behaviour decision — pin the expected behaviour in the test).

## 3. Failing tests (red) — origin derivation

- [ ] 3.1 Write `test_origin_strips_default_http_port` — `_origin_from_url("http://example.com:80/path")` returns `"http://example.com"`.
- [ ] 3.2 Write `test_origin_strips_default_https_port` — `_origin_from_url("https://EXAMPLE.com:443/")` returns `"https://example.com"` (lower-cases host).
- [ ] 3.3 Write `test_origin_preserves_non_default_port` — `_origin_from_url("http://127.0.0.1:9123/locate_l1.html")` returns `"http://127.0.0.1:9123"`.
- [ ] 3.4 Write `test_origin_drops_path_query_fragment` — `_origin_from_url("http://x.test/a/b?q=1#f") == "http://x.test"`.
- [ ] 3.5 Write `test_origin_lowercases_scheme_and_host` — `_origin_from_url("HTTP://X.TEST/") == "http://x.test"`.

## 4. Failing tests (red) — `locate()` cache integration

- [ ] 4.1 Reuse the `_make_chat_stub` helper pattern from existing locate tests. Add a `fail_if_called=True` mode if the existing helper does not already expose one.
- [ ] 4.2 Write `test_first_resolve_writes_cache_returns_l1_tier` — load `locate_l1.html` (existing fixture), construct a `LocatorCache(path=":memory:")`; call `locate(b._page, "Submit button", llm_chat=fail_if_called_stub, cache=cache)`; assert returned `tier == "L1_ax"`; assert `cache.get(origin=..., intent="Submit button")` returns a `CacheEntry` with `tier="L1_ax"`, the same `selector` as the result, and a non-empty `ax_fingerprint`.
- [ ] 4.3 Write `test_second_resolve_hits_cache_skips_llm` — same fixture / cache as 4.2; after the first `locate(...)` call, call `locate(...)` a second time with a fresh `fail_if_called_stub`; assert returned `tier == "cache"`; assert `result.selector` equals the cached `selector`; assert `result.ax_fingerprint` equals the stored `ax_fingerprint`; assert the fail-if-called stub was never invoked.
- [ ] 4.4 Write `test_drift_invalidates_cache_and_replaces_row` — using `cache_drift.html`: first `locate(b._page, "Submit button", cache=cache)` writes a row; then `b._page.evaluate("__rename('Send')")` mutates the button's accessible name; second `locate(b._page, "Submit button", cache=cache)` SHALL return `tier == "L1_ax"` (NOT `"cache"`) — wait, the renamed button no longer has accessible name `Submit`, so L1 will return `zero_matches`. Adjust: the test should assert the second call raises `LocatorMiss(reason="zero_matches")` AND the cache row has been deleted (`cache.get(...) is None`). Alternatively (and this is the variant we keep): after `__rename('Send')`, immediately `__add('Submit')` so a NEW Submit button exists at a different DOM location; the second `locate(...)` then succeeds via L1 against the new element, the cache row is replaced, and the new row's `ax_fingerprint` reflects the new element. Pin the latter variant in the test.
- [ ] 4.5 Write `test_removed_element_invalidates_cache_and_falls_through` — using `cache_drift.html`: first `locate(...)` writes a row; `b._page.evaluate("__remove()")`; then `b._page.evaluate("__add('Submit')")`; second `locate(...)` SHALL succeed with `tier == "L1_ax"`, and the cache SHALL contain the new row (replaced).
- [ ] 4.6 Write `test_origin_scoping_two_servers` — start two `fixture_server` instances on different ports (using the factory from task 1.2); load `locate_l1.html` from each into two separate Browser contexts; first `locate(...)` against server A writes a row; `locate(...)` against server B with the same intent SHALL NOT hit the cache (`tier != "cache"`); the cache SHALL contain two rows after the second call.
- [ ] 4.7 Write `test_intent_scoping_same_page` — load a fixture page that has both a `<button>Submit</button>` and a `<button>Cancel</button>`; first `locate(b._page, "Submit button", cache=cache)`; second `locate(b._page, "Cancel button", cache=cache)`; assert the second call's `tier != "cache"` and the cache contains two rows. (If no existing fixture has both buttons in distinct unambiguous form, add a tiny `task2/tests/fixtures/cache_two_intents.html`; otherwise reuse an existing one.)
- [ ] 4.8 Write `test_l4_cached_entry_forced_miss_on_read` — directly insert an `L4_vision` `CacheEntry` (with `selector=""`, `coords=(100, 50)`, an arbitrary fingerprint) into the cache for `(origin=<page origin>, intent="Submit button")` against the `locate_l1.html` page; call `locate(b._page, "Submit button", llm_chat=fail_if_called_stub, cache=cache)`; assert returned `tier == "L1_ax"` (NOT `"cache"`); assert the LLM stub was not invoked (L1 succeeds without it); assert the cache row's `tier` is now `"L1_ax"` (replaced).
- [ ] 4.9 Write `test_cache_none_preserves_prior_behaviour` — no `cache=` argument; `locate(b._page, "Submit button")` against `locate_l1.html`; assert `tier == "L1_ax"`; assert no SQLite file was created in the cwd or a sentinel temp dir (verify by checking that no `LocatorCache` instance was created — indirectly by inspecting that `agent.locator_cache._created_count` did not increment, OR by structuring the test so this is observable; if not easily testable, drop this scenario from the suite and note the rationale in commit).
- [ ] 4.10 Write `test_cache_hit_does_not_call_get_by_role` — instrument the test by passing a stub `llm_chat` that fails if called AND by sanity-checking that the second call is meaningfully cheaper than the first. Soft assertion: pass through `fail_if_called_stub` only.
- [ ] 4.11 Write `test_cache_failure_does_not_write_row` — call `locate(b._page, "Refund button", cache=cache)` against a page that has no Refund button (so all four tiers miss); assert the call raises `LocatorMiss`; assert `cache.get(origin=..., intent="Refund button")` returns `None` (the failure path SHALL NOT write to the cache).
- [ ] 4.12 From `task2/`, run `uv run pytest tests/agent/test_locator_cache.py -x` and confirm every test fails for the expected reason (missing module, missing class, missing parameter).

## 5. Implementation (green) — `LocatorCache` module

- [ ] 5.1 Create `task2/agent/locator_cache.py`. Module-level imports: `from __future__ import annotations`, `import sqlite3`, `from dataclasses import dataclass`, `from datetime import UTC, datetime`, `from urllib.parse import urlsplit`. Do NOT import `agent.llm`, `agent.locate`, `agent.browser`, or `playwright`.
- [ ] 5.2 Define the frozen `CacheEntry` dataclass with the fields specified in `design.md` and the spec: `origin`, `intent`, `role`, `name`, `selector`, `ax_fingerprint`, `confidence`, `tier`, `coords`, `written_at_utc`.
- [ ] 5.3 Define `_EXPECTED_COLUMNS: tuple[tuple[str, str], ...] = ((..., ...), ...)` listing the expected column names and SQLite types in canonical order.
- [ ] 5.4 Implement `_origin_from_url(url: str) -> str` per the canonical rule (lower-case scheme, lower-case host, drop default 80/443, preserve other ports). Use `urllib.parse.urlsplit` and string formatting; do NOT depend on `urllib.parse.urlparse`'s `netloc` directly without canonicalisation.
- [ ] 5.5 Implement `LocatorCache.__init__(self, *, path: str = ":memory:")` to open the SQLite connection, run `_ensure_schema()` (drop-on-mismatch + create), and store the connection on `self._conn`.
- [ ] 5.6 Implement `_ensure_schema(self)`: query `PRAGMA table_info(locator_cache)`. If the result's column-name+type set does not match `_EXPECTED_COLUMNS`, run `DROP TABLE IF EXISTS locator_cache` and recreate. Commit.
- [ ] 5.7 Implement `LocatorCache.get(self, *, origin: str, intent: str) -> CacheEntry | None` — `SELECT ... FROM locator_cache WHERE origin = ? AND intent = ? LIMIT 1`. Return a `CacheEntry` constructed from the row, or `None`.
- [ ] 5.8 Implement `LocatorCache.put(self, entry: CacheEntry) -> None` — `INSERT OR REPLACE INTO locator_cache (...) VALUES (...)`. Commit.
- [ ] 5.9 Implement `LocatorCache.invalidate(self, *, origin: str, intent: str) -> None` — `DELETE FROM locator_cache WHERE origin = ? AND intent = ?`. Commit. Silent on no-op.
- [ ] 5.10 Implement `LocatorCache.close(self) -> None` — close the connection if not already closed; idempotent.
- [ ] 5.11 Implement `__enter__` / `__exit__` returning `self` and calling `close()` respectively.
- [ ] 5.12 From `task2/`, run `uv run pytest tests/agent/test_locator_cache.py::test_construct_in_memory_default tests/agent/test_locator_cache.py::test_put_then_get_round_trips ...` (the unit-test subset from sections 2 and 3) and confirm they pass. The integration tests from section 4 will still fail until step 6.

## 6. Implementation (green) — `locate()` integration

- [ ] 6.1 In `task2/agent/locate.py`, add `coords: tuple[int, int] | None = None` to the `LocateResult` dataclass *if it is not already present* (it was added by ticket #6 — verify, do not duplicate).
- [ ] 6.2 In `task2/agent/locate.py`, modify the `locate(...)` signature to add a keyword-only parameter `cache: LocatorCache | None = None`. Use a `TYPE_CHECKING` import for `LocatorCache` to avoid pulling `sqlite3` in at module load when callers do not pass a cache.
- [ ] 6.3 Inside `locate()`:
  - Compute `role, name = parse_intent(intent)`.
  - If `cache is not None`: compute `origin = _origin_from_url(page.url)` (import the helper lazily from `agent.locator_cache`); call `cache.get(origin=origin, intent=intent)`. If a row exists, attempt cache-hit logic per design.md:
    - If `entry.tier == "L4_vision"`: `cache.invalidate(origin=origin, intent=intent)`. Continue to ladder.
    - Else: re-resolve via `page.locator(entry.selector)`. If `count() == 0`: invalidate, continue. Else: compute the canonical L1-style fingerprint of `locator.first` (use the existing `_ACCESSIBLE_NAME_JS`). Compare with `entry.ax_fingerprint`. If equal: return `LocateResult(tier="cache", role=entry.role, name=entry.name, selector=entry.selector, ax_fingerprint=entry.ax_fingerprint, confidence=entry.confidence, coords=entry.coords)`. If unequal: invalidate, continue.
  - Run the existing L1 → L2/L3/L4 cascade unchanged. Catch exceptions, return result.
  - If `cache is not None` and the ladder succeeded: build a `CacheEntry` from the result. For non-L4 results, recompute the canonical L1-style fingerprint over the resolved element via `page.locator(result.selector).first`; for L4 results, reuse the L4 vision fingerprint as the stored value. Use `datetime.now(UTC).isoformat(timespec="seconds")` (with `Z` suffix replacement of `+00:00`) for `written_at_utc`. Call `cache.put(entry)`.
  - Return the result.
- [ ] 6.4 Add a small private helper `_canonical_ax_fingerprint(page: Page, *, role: str, selector: str) -> str | None` that re-resolves the selector, returns `None` if `count() == 0`, otherwise runs `_ACCESSIBLE_NAME_JS` against `.first` and returns `sha256(f"{role}:{accessible_name}".encode()).hexdigest()`. Used both for cache probe revalidation and for write-time fingerprinting.
- [ ] 6.5 Update the `LocateResult.tier` Literal annotation (if one was introduced in ticket #6 — verify) to include `"cache"`. If `tier` is currently typed as `str`, leave it as `str`; the spec already permits the new value at the `str` level.
- [ ] 6.6 From `task2/`, run `uv run pytest tests/agent/test_locator_cache.py` and confirm all integration tests in section 4 now pass.
- [ ] 6.7 From `task2/`, run `uv run pytest` (full suite) and confirm tickets #1–#6 tests still pass — in particular `test_locate.py`, `test_locate_l2.py`, `test_locate_l3.py`, `test_locate_l4.py`, and `test_browser.py` are unaffected.

## 7. Refactor + housekeeping

- [ ] 7.1 Reread `task2/agent/locator_cache.py`. Look for: SQL string duplication (consolidate INSERT/SELECT column lists into a constant), magic string literals (lift `LOCATOR_CACHE_TABLE = "locator_cache"`), missing type hints on private helpers.
- [ ] 7.2 Reread `task2/agent/locate.py`. Confirm: `agent.locator_cache` is imported lazily inside `locate()` and NOT at module top level. Verify by reading the imports section. Confirm: existing L1/L2/L3/L4 functions are unchanged in body except where `coords` field was already added.
- [ ] 7.3 Confirm `LocateResult.coords` default is `None` and existing callers do not need updates.
- [ ] 7.4 Run `uv run ruff format .` from `task2/` (no changes after green) and `uv run ruff check .` (clean).
- [ ] 7.5 Confirm no new dependencies were added to `task2/pyproject.toml`.

## 8. Validation

- [ ] 8.1 Run `openspec validate implement-locator-cache --strict` — change SHALL be valid.
- [ ] 8.2 Final pre-commit gate from `task2/`: `uv run ruff format .` (no changes), `uv run ruff check .` (clean), `uv run pytest` (all tests pass).
- [ ] 8.3 Conventional commits on the branch:
  - `chore(task2): scaffold implement-locator-cache` (created at scaffolding — counts).
  - `test(task2): add failing locator-cache tests and drift fixture`.
  - `feat(task2): add LocatorCache module and SQLite schema`.
  - `feat(task2): wire LocatorCache into locate() with AX-fingerprint revalidation`.
  - `refactor(task2): <whatever 7.1 ends up doing>` — only if a real cleanup happens; skip otherwise.
- [ ] 8.4 No hooks bypassed at any point.
