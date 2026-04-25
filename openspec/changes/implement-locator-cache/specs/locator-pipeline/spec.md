## MODIFIED Requirements

### Requirement: Locator pipeline entry point

The system SHALL expose `agent.locate.locate(page, intent, *, llm_chat=None, cache=None)` as the single entry point for resolving a natural-language intent to a unique element on the currently loaded Playwright page. `locate` SHALL parse the intent into `(role, name)` and call `locate_l1`. If `locate_l1` raises `LocatorMiss(reason="zero_matches")`, `locate` SHALL fall through to `locate_l2(page, role=role, name=name)`; if `locate_l2` raises `LocatorMiss`, `locate` SHALL fall through to `locate_l4(page, role=role, name=name, intent=intent, llm_chat=llm_chat)` and return its result (or propagate its `LocatorMiss`). If `locate_l1` raises `LocatorMiss(reason="ambiguous")`, `locate` SHALL fall through to `locate_l3(page, role=role, name=name, llm_chat=llm_chat)`; if `locate_l3` raises `LocatorMiss`, `locate` SHALL fall through to `locate_l4(...)` and return its result (or propagate its `LocatorMiss`). The `llm_chat` parameter SHALL be forwarded to `locate_l3` and `locate_l4`; passing `None` (the default) means the downstream tier will resolve the default `agent.llm.chat` lazily.

When `cache is not None`, `locate` SHALL probe and update the cache as follows:

1. **Probe**: derive `origin` from `page.url` using the canonical origin rule defined in the `locator-cache` capability. Call `cache.get(origin=origin, intent=intent)`. If the call returns a `CacheEntry`:
   - If the entry's `tier` is `"L4_vision"`: invalidate the row via `cache.invalidate(origin=origin, intent=intent)` and continue to the resolve step. No L4 vision call SHALL be made during the probe.
   - Otherwise: re-resolve the cached `selector` via `page.locator(entry.selector)`. If `count() == 0`, invalidate the row and continue to the resolve step. If `count() >= 1`, recompute the canonical AX fingerprint of `locator.first` using the same rule the cache uses at write time, and compare against `entry.ax_fingerprint`. On equality, return a `LocateResult(tier="cache", role=entry.role, name=entry.name, selector=entry.selector, ax_fingerprint=entry.ax_fingerprint, confidence=entry.confidence, coords=entry.coords)` immediately — no L1–L4 work SHALL be done, no LLM call SHALL be made. On inequality, invalidate the row and continue to the resolve step.

2. **Resolve**: run the L1 → L2/L3/L4 cascade exactly as defined when `cache is None`.

3. **Write**: after a successful resolve at any tier, build a `CacheEntry` from the resolved `LocateResult` (recomputing the canonical AX fingerprint over the resolved element for non-L4 results; using the L4 vision fingerprint for L4 results) plus the current UTC timestamp, and call `cache.put(entry)` before returning the `LocateResult`.

When `cache is None`, behaviour SHALL be identical to the cache-less specification: no probe, no write, no invalidate.

On success `locate` SHALL return a `LocateResult`. On failure it SHALL raise either `LocatorMiss` (UI-state failure — element absent or unresolvable after all wired-in tiers) or `IntentParseError` (the intent itself could not be parsed). The cache SHALL NOT be written on failure.

#### Scenario: Resolves a parseable intent via L1

- **GIVEN** a page exposing exactly one accessible element matching role `button` and accessible name `Submit`
- **WHEN** a caller invokes `locate(page, "Submit button")`
- **THEN** the call SHALL return a `LocateResult`
- **AND** `result.tier` SHALL equal `"L1_ax"`
- **AND** `result.role` SHALL equal `"button"`
- **AND** `result.name` SHALL equal `"Submit"`

#### Scenario: Falls through to L2 on L1 zero-match

- **GIVEN** a page where no element matches role `textbox` with accessible name `Email address` (so L1 returns zero matches)
- **AND** the page contains exactly one `<input placeholder="Email address">` resolvable by L2's placeholder strategy
- **WHEN** a caller invokes `locate(page, "Email address textbox")`
- **THEN** the call SHALL return a `LocateResult`
- **AND** `result.tier` SHALL equal `"L2_dom"`

#### Scenario: Falls through to L3 on L1 ambiguous

- **GIVEN** a page where two or more accessible buttons share the name `Save` (L1 returns `LocatorMiss(reason="ambiguous", match_count=N)`)
- **AND** a stub `llm_chat` that returns `{"index": 0}`
- **WHEN** a caller invokes `locate(page, "Save button", llm_chat=stub)`
- **THEN** the call SHALL return a `LocateResult`
- **AND** `result.tier` SHALL equal `"L3_rerank"`

#### Scenario: Surfaces unparseable intent

- **WHEN** a caller invokes `locate(page, "do the thing")` with no recognised trailing role keyword
- **THEN** the call SHALL raise `IntentParseError`
- **AND** the exception message SHALL include the offending intent string

#### Scenario: First resolve writes to the cache

- **GIVEN** a page exposing exactly one accessible button named `Submit`
- **AND** a freshly constructed empty `LocatorCache(path=":memory:")`
- **AND** a stub `llm_chat` that fails the test if invoked
- **WHEN** a caller invokes `locate(page, "Submit button", llm_chat=stub, cache=cache)`
- **THEN** the call SHALL return a `LocateResult` with `tier == "L1_ax"` (a non-cache tier)
- **AND** the cache SHALL contain exactly one `CacheEntry` for `(origin=<page origin>, intent="Submit button")`
- **AND** that entry's `selector` SHALL equal the returned `LocateResult.selector`
- **AND** that entry's `tier` SHALL equal `"L1_ax"`

#### Scenario: Second resolve hits the cache without invoking the LLM stub

- **GIVEN** a page exposing exactly one accessible button named `Submit`
- **AND** a `LocatorCache` and a prior `locate(page, "Submit button", cache=cache)` call that wrote a row
- **AND** a stub `llm_chat` that fails the test if invoked
- **WHEN** a caller invokes `locate(page, "Submit button", llm_chat=stub, cache=cache)` a second time against the same DOM
- **THEN** the call SHALL return a `LocateResult` with `tier == "cache"`
- **AND** `result.selector` SHALL equal the previously cached `selector`
- **AND** `result.ax_fingerprint` SHALL equal the previously stored `ax_fingerprint`
- **AND** the LLM stub SHALL NOT have been invoked
- **AND** the cache SHALL still contain the entry (no invalidation occurred)

#### Scenario: AX-fingerprint mismatch invalidates the cache and falls through

- **GIVEN** a page with a Submit button, a `LocatorCache`, and a successful prior `locate(...)` that wrote a row
- **WHEN** the page is mutated so the cached selector now resolves to an element whose accessible name is `Send` (different fingerprint)
- **AND** a caller invokes `locate(page, "Submit button", cache=cache)` a second time
- **THEN** the call SHALL return a `LocateResult` whose `tier` is NOT `"cache"`
- **AND** the cache SHALL contain a row whose `ax_fingerprint` reflects the *new* element (the row has been replaced, not just deleted)

#### Scenario: Cached selector resolves to zero elements invalidates and falls through

- **GIVEN** a page with a Submit button, a `LocatorCache`, and a successful prior `locate(...)` that wrote a row for `intent="Submit button"`
- **WHEN** the page is mutated so the cached element is removed from the DOM (no element matches the cached selector)
- **AND** an alternate accessible button named `Submit` is added at a different point in the DOM (so the L1 ladder will resolve again)
- **AND** a caller invokes `locate(page, "Submit button", cache=cache)` a second time
- **THEN** the call SHALL return a `LocateResult` whose `tier` is NOT `"cache"`
- **AND** the cache SHALL contain a fresh row for the new element

#### Scenario: Cache is scoped by origin

- **GIVEN** two pages served on different origins (e.g. `http://127.0.0.1:9001` and `http://127.0.0.1:9002`), each containing one accessible button named `Submit`
- **AND** a single `LocatorCache` shared between resolves
- **WHEN** a caller invokes `locate(page_a, "Submit button", cache=cache)` against the first page
- **AND** then invokes `locate(page_b, "Submit button", cache=cache)` against the second page
- **THEN** the second call SHALL NOT return a `LocateResult` with `tier == "cache"`
- **AND** the cache SHALL contain two distinct rows, one per origin

#### Scenario: Cache is scoped by intent

- **GIVEN** a single page exposing one button named `Submit` and one button named `Cancel`
- **AND** a single `LocatorCache`
- **WHEN** a caller invokes `locate(page, "Submit button", cache=cache)` and then `locate(page, "Cancel button", cache=cache)`
- **THEN** the second call SHALL NOT return a `LocateResult` with `tier == "cache"`
- **AND** the cache SHALL contain two distinct rows, one per intent

#### Scenario: L4-cached entry is forced-miss on read

- **GIVEN** a `LocatorCache` containing a row whose `tier == "L4_vision"` for some `(origin, intent)` (written by a prior L4 resolve)
- **AND** a page where the same intent now resolves via L1
- **AND** a stub `llm_chat` that fails the test if invoked
- **WHEN** a caller invokes `locate(page, intent, llm_chat=stub, cache=cache)`
- **THEN** the call SHALL return a `LocateResult` whose `tier` is NOT `"cache"`
- **AND** the cache row's `tier` after the call SHALL equal `"L1_ax"` (replaced via the fall-through resolve)
- **AND** the LLM stub SHALL NOT have been invoked (since L1 succeeds without it)

#### Scenario: cache=None preserves prior behaviour

- **GIVEN** a page exposing exactly one accessible button named `Submit`
- **WHEN** a caller invokes `locate(page, "Submit button")` with no `cache` argument
- **THEN** the call SHALL return a `LocateResult` with `tier == "L1_ax"`
- **AND** no SQLite database SHALL have been opened anywhere as a side effect of this call

### Requirement: `LocateResult` shared shape

The system SHALL define `agent.locate.LocateResult` as a dataclass with the fields `tier: str`, `role: str`, `name: str | None`, `selector: str`, `ax_fingerprint: str`, `confidence: float`, and `coords: tuple[int, int] | None`. The `tier` field SHALL accept the values `"L1_ax"`, `"L2_dom"`, `"L3_rerank"`, `"L4_vision"`, and `"cache"`. The `"cache"` value SHALL be produced only by the locator-pipeline entry point on a cache hit; the L1–L4 resolver functions SHALL never emit `"cache"`. This shape SHALL remain the contract between the locator pipeline and its consumers (the agent loop, the supervisor, the locator cache, the trace writer).

#### Scenario: Result is constructible and round-trippable through Playwright

- **GIVEN** a `LocateResult` returned by `locate_l1` for a unique button
- **WHEN** a caller invokes `page.locator(result.selector)`
- **THEN** the resulting Playwright `Locator` SHALL refer to the same DOM element that produced the result

#### Scenario: AX fingerprint is deterministic for the same role+name

- **WHEN** two `LocateResult`s are produced by L1 for the same `(role, name)` pair against accessibility nodes that share the same role and accessible name
- **THEN** their `ax_fingerprint` values SHALL be equal

#### Scenario: Cache-tier result reuses the stored confidence

- **GIVEN** a cached row with `tier="L1_ax"` and `confidence=1.0`
- **WHEN** `locate()` returns a cache-hit `LocateResult` for that row
- **THEN** the returned `LocateResult.tier` SHALL equal `"cache"`
- **AND** the returned `LocateResult.confidence` SHALL equal `1.0`
