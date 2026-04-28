# locator-pipeline Specification

## Purpose
TBD - created by archiving change implement-locate-l1. Update Purpose after archive.
## Requirements
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

### Requirement: Intent parser

The system SHALL provide `agent.locate.parse_intent(intent: str) -> tuple[str, str | None]` that turns a natural-language intent into `(role, name)`. The parser SHALL strip a single leading article (`the`, `a`, `an`, case-insensitive) if present, then treat the final whitespace-separated token as the role and the remaining tokens (joined by single spaces) as the accessible name. If no leading text remains, the name SHALL be `None`. The role token SHALL be lowercased, normalized through the role-alias map, and validated against the supported role set: `button`, `link`, `textbox`, `checkbox`, `heading`, `list`, `listitem`. The role-alias map SHALL include at least `items -> listitem` and `lists -> list` so that natural-language plural phrasings emitted by the production LLM resolve to canonical roles. Unknown roles SHALL raise `IntentParseError`. Empty or whitespace-only intents SHALL raise `IntentParseError`.

The supported role set SHALL be defined as a `Literal` alias so callers can type-check against it:

- `SupportedRole = Literal["button", "link", "textbox", "checkbox", "heading", "list", "listitem"]`

#### Scenario: Parses "<name> <role>"

- **WHEN** a caller invokes `parse_intent("Submit button")`
- **THEN** the call SHALL return `("button", "Submit")`

#### Scenario: Strips leading article

- **WHEN** a caller invokes `parse_intent("the Submit button")`
- **THEN** the call SHALL return `("button", "Submit")`

#### Scenario: Multi-word names

- **WHEN** a caller invokes `parse_intent("Email address textbox")`
- **THEN** the call SHALL return `("textbox", "Email address")`

#### Scenario: Bare role with no name

- **WHEN** a caller invokes `parse_intent("button")`
- **THEN** the call SHALL return `("button", None)`

#### Scenario: Unknown role rejected

- **WHEN** a caller invokes `parse_intent("Submit widget")`
- **THEN** the call SHALL raise `IntentParseError`
- **AND** the exception message SHALL include the offending role token `"widget"`

#### Scenario: Empty intent rejected

- **WHEN** a caller invokes `parse_intent("   ")`
- **THEN** the call SHALL raise `IntentParseError`

#### Scenario: Bare list role with no name

- **WHEN** a caller invokes `parse_intent("list")`
- **THEN** the call SHALL return `("list", None)`

#### Scenario: Bare listitem role with no name

- **WHEN** a caller invokes `parse_intent("listitem")`
- **THEN** the call SHALL return `("listitem", None)`

#### Scenario: listitem role with a name

- **WHEN** a caller invokes `parse_intent("Items listitem")`
- **THEN** the call SHALL return `("listitem", "Items")`

#### Scenario: items token aliases to listitem

- **WHEN** a caller invokes `parse_intent("items")`
- **THEN** the call SHALL return `("listitem", None)`

#### Scenario: lists token aliases to list

- **WHEN** a caller invokes `parse_intent("lists")`
- **THEN** the call SHALL return `("list", None)`

#### Scenario: production phrasing "list items" parses

- **WHEN** a caller invokes `parse_intent("list items")`
- **THEN** the call SHALL return `("listitem", "list")`

### Requirement: L1 accessibility-tree resolution

The system SHALL provide `agent.locate.locate_l1(page, *, role, name) -> LocateResult` that resolves an element via Playwright's accessibility-tree query (`page.get_by_role(role, name=name, exact=False)` when `name` is provided, else `page.get_by_role(role)`). When exactly one element matches, `locate_l1` SHALL return a `LocateResult` carrying `tier="L1_ax"`, the queried `role` and `name`, a Playwright role-locator string in `selector`, an `ax_fingerprint` derived from `role + accessible name`, and `confidence=1.0`. When zero elements match, `locate_l1` SHALL raise `LocatorMiss(reason="zero_matches")`. When two or more elements match, `locate_l1` SHALL raise `LocatorMiss(reason="ambiguous")` carrying the match count; it SHALL NOT pick arbitrarily.

#### Scenario: Unique role+name match returns the AX-resolved element

- **GIVEN** a page containing `<button>Submit</button>` and a `<div role="button" aria-label="Cancel">` (different accessible name)
- **WHEN** a caller invokes `locate_l1(page, role="button", name="Submit")`
- **THEN** the call SHALL return a `LocateResult` with `tier == "L1_ax"`
- **AND** the resolved Playwright `Locator` (constructed from `result.selector`) SHALL refer to the real `<button>` element, not the spoofer
- **AND** `result.confidence` SHALL equal `1.0`
- **AND** `result.ax_fingerprint` SHALL be a non-empty string

#### Scenario: Non-semantic look-alikes are invisible to L1

- **GIVEN** a page containing a `<div class="btn">Submit</div>` element with no `role` or `aria-*` attributes and no other element matching role `button` with accessible name `Submit`
- **WHEN** a caller invokes `locate_l1(page, role="button", name="Submit")`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"zero_matches"`

#### Scenario: Ambiguous AX matches refuse to pick

- **GIVEN** a page containing `<button>Save</button>` in two distinct sections, both with accessible name `Save` and role `button`
- **WHEN** a caller invokes `locate_l1(page, role="button", name="Save")`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"ambiguous"`
- **AND** `LocatorMiss.match_count` SHALL equal `2`

#### Scenario: Bare role query

- **GIVEN** a page containing exactly one `<h1>Welcome</h1>` and no other heading elements
- **WHEN** a caller invokes `locate_l1(page, role="heading", name=None)`
- **THEN** the call SHALL return a `LocateResult` with `tier == "L1_ax"` and `role == "heading"`

### Requirement: L2 DOM-heuristic resolution

The system SHALL provide `agent.locate.locate_l2(page, *, role, name) -> LocateResult` that resolves an element via DOM heuristics, intended to catch the cases L1 misses (elements with no accessible name). For each supported role, `locate_l2` SHALL run the role's L2 strategy (currently exactly one per role; future tickets may add additional strategies per role). When the role's strategy yields exactly one element, `locate_l2` SHALL return a `LocateResult`. When the strategy yields zero elements, `locate_l2` SHALL raise `LocatorMiss(reason="zero_matches", match_count=0)`. When the strategy yields more than one element, `locate_l2` SHALL raise `LocatorMiss(reason="ambiguous", match_count=N)` where `N` is the strategy's match count. `locate_l2` SHALL NOT pick arbitrarily.

The supported role-to-strategy mapping:

1. **Placeholder strategy** — for `role == "textbox"` (with non-empty `name`). Uses Playwright's placeholder query (`page.get_by_placeholder(name, exact=False)`).
2. **Text-contains over a clickable taxonomy** — for `role` in `{"button", "link"}` (with non-empty `name`). Restricts the candidate set to a per-role CSS taxonomy that includes non-semantic clickables (for `button`: `button, input[type=button], input[type=submit], input[type=reset], [role=button], [onclick], [class*="btn"], [class*="button"]`; for `link`: `a[href], [role=link]`), then filters by visible text via `Locator.filter(has_text=name)`.

Roles outside the supported set (`heading`, `checkbox`, plus any role added later that L2 does not know how to handle) SHALL cause `locate_l2` to raise `LocatorMiss(reason="zero_matches", match_count=0)` immediately, without running any strategy. Calls with an empty `name` for roles that require one SHALL likewise short-circuit with `zero_matches`.

On success, `LocateResult` SHALL be populated with `tier="L2_dom"`, the queried `role` and `name`, a Playwright-locatable `selector` string that re-resolves to the same single element when passed to `page.locator(...)`, an `ax_fingerprint` derived from `role + ":" + name + ":" + winning_strategy_id`, and `confidence=0.7`. The fingerprint SHALL NOT include the matched element's DOM path or class names — that is the property the cache (a later ticket) relies on to survive cosmetic CSS changes.

#### Scenario: Placeholder-only textbox is resolved via L2

- **GIVEN** a page containing exactly one element matching `<input placeholder="Email address">` with no associated `<label>`, no `aria-label`, no `aria-labelledby`, and no enclosing `<label>`
- **WHEN** a caller invokes `locate_l2(page, role="textbox", name="Email address")`
- **THEN** the call SHALL return a `LocateResult`
- **AND** `result.tier` SHALL equal `"L2_dom"`
- **AND** `result.confidence` SHALL equal `0.7`
- **AND** `page.locator(result.selector)` SHALL resolve to that single `<input>` element

#### Scenario: Non-semantic clickable is resolved via text-contains

- **GIVEN** a page containing exactly one `<div class="btn" onclick="...">Submit</div>` and no other element whose visible text contains `"Submit"` within the button taxonomy
- **WHEN** a caller invokes `locate_l2(page, role="button", name="Submit")`
- **THEN** the call SHALL return a `LocateResult` with `tier == "L2_dom"`
- **AND** `page.locator(result.selector)` SHALL resolve to that single `<div>` element

#### Scenario: Ambiguous L2 raises with the strategy's match count

- **GIVEN** a page containing two `<div class="btn">Save</div>` elements in distinct sections and no other elements matching the `button` taxonomy with text `"Save"`
- **WHEN** a caller invokes `locate_l2(page, role="button", name="Save")`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"ambiguous"`
- **AND** `LocatorMiss.match_count` SHALL equal `2`

#### Scenario: Strategy misses raises zero_matches

- **GIVEN** a page containing no element whose placeholder, accessible name, or visible text within the relevant taxonomy contains `"Refund"`
- **WHEN** a caller invokes `locate_l2(page, role="button", name="Refund")`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"zero_matches"`
- **AND** `LocatorMiss.match_count` SHALL equal `0`

#### Scenario: Unsupported role short-circuits

- **WHEN** a caller invokes `locate_l2(page, role="heading", name="Welcome")`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"zero_matches"`
- **AND** `LocatorMiss.match_count` SHALL equal `0`
- **AND** `locate_l2` SHALL NOT have invoked any DOM query against the page

#### Scenario: AX fingerprint is independent of class and DOM path

- **GIVEN** two pages each containing exactly one `<div onclick="...">Submit</div>` matching the L2 button taxonomy via the text-contains strategy, but with different `class` attributes and different parent structures
- **WHEN** a caller invokes `locate_l2(page, role="button", name="Submit")` against each
- **THEN** the two `LocateResult.ax_fingerprint` values SHALL be equal

### Requirement: L3 semantic-rerank resolution

The system SHALL provide `agent.locate.locate_l3(page, *, role, name, llm_chat=None) -> LocateResult` that resolves an element by asking an LLM to pick among the AX-tree candidates that share `role` and accessible name `name`. `locate_l3` SHALL re-query candidates via `page.get_by_role(role, name=name, exact=False)`. When the candidate count is `0`, `locate_l3` SHALL raise `LocatorMiss(reason="zero_matches", match_count=0)`. When the candidate count is `1`, `locate_l3` SHALL return that single element directly as `LocateResult` with `tier="L3_rerank"` and `confidence=0.8` (no LLM call SHALL be made). When the candidate count is `≥ 2`, `locate_l3` SHALL build a rerank prompt containing up to `K = 10` candidates — each described by its accessible name, nearest section heading (truncated to 100 characters), and a bounded nearby-text snippet (truncated to 200 characters) — invoke `llm_chat` (defaulting to `agent.llm.chat` when the parameter is `None`), parse the LLM's reply as JSON, and return the candidate at the integer `index` field. If the LLM reply is not valid JSON, lacks an integer `index` field, or the index is outside `[0, K)` where K is the number of candidates considered, `locate_l3` SHALL raise `LocatorMiss(reason="ambiguous", match_count=N)` where `N` is the candidate count.

On success, `LocateResult` SHALL be populated with `tier="L3_rerank"`, the queried `role` and `name`, a Playwright-locatable `selector` of the form `f'role={role}[name="{escaped name}" i] >> nth={chosen_index}'` that re-resolves to the same single element when passed to `page.locator(...)`, an `ax_fingerprint` derived from `sha256(f"{role}:{name}:{section_heading}".encode()).hexdigest()` where `section_heading` is the chosen candidate's nearest section heading (the same value passed to the LLM), and `confidence=0.8`. The fingerprint SHALL NOT include the matched element's class names, DOM path, or chosen index — those are the signals the cache (later ticket) needs to be robust against.

`locate_l3` SHALL NOT be invoked by L1 or L2; it is reachable directly or via `locate()`'s ambiguous-cascade.

#### Scenario: Three same-named buttons in distinct sections are disambiguated by the LLM

- **GIVEN** a page containing three `<button>Save</button>` elements, each inside a distinct `<section>` with a distinct heading (e.g. "Profile", "Settings", "Documents")
- **AND** a stub `llm_chat` that returns a `ChatResponse` whose `content` is exactly the JSON string `{"index": 1}`
- **WHEN** a caller invokes `locate_l3(page, role="button", name="Save", llm_chat=stub)`
- **THEN** the call SHALL return a `LocateResult` with `tier == "L3_rerank"`
- **AND** `result.confidence` SHALL equal `0.8`
- **AND** `result.role` SHALL equal `"button"` and `result.name` SHALL equal `"Save"`
- **AND** `page.locator(result.selector)` SHALL resolve to a single element
- **AND** that element SHALL be the second of the three `<button>Save</button>` elements in DOM order
- **AND** `result.ax_fingerprint` SHALL be a non-empty string

#### Scenario: Single candidate returns directly without invoking the LLM

- **GIVEN** a page exposing exactly one accessible element matching role `button` and accessible name `Submit`
- **AND** a stub `llm_chat` that fails the test if invoked (e.g. raises an `AssertionError` when called)
- **WHEN** a caller invokes `locate_l3(page, role="button", name="Submit", llm_chat=stub)`
- **THEN** the call SHALL return a `LocateResult` with `tier == "L3_rerank"`
- **AND** the stub SHALL NOT have been invoked

#### Scenario: Zero candidates raises zero_matches without invoking the LLM

- **GIVEN** a page with no element matching role `button` and accessible name `Refund`
- **AND** a stub `llm_chat` that fails the test if invoked
- **WHEN** a caller invokes `locate_l3(page, role="button", name="Refund", llm_chat=stub)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"zero_matches"`
- **AND** `LocatorMiss.match_count` SHALL equal `0`
- **AND** the stub SHALL NOT have been invoked

#### Scenario: Malformed LLM reply raises ambiguous

- **GIVEN** a page with three same-named candidates as above
- **AND** a stub `llm_chat` that returns a `ChatResponse` whose `content` is the string `not even close to JSON`
- **WHEN** a caller invokes `locate_l3(page, role="button", name="Save", llm_chat=stub)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"ambiguous"`
- **AND** `LocatorMiss.match_count` SHALL equal `3`

#### Scenario: Out-of-range LLM index raises ambiguous

- **GIVEN** a page with three same-named candidates
- **AND** a stub `llm_chat` that returns a `ChatResponse` whose `content` is `{"index": 99}`
- **WHEN** a caller invokes `locate_l3(page, role="button", name="Save", llm_chat=stub)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"ambiguous"`
- **AND** `LocatorMiss.match_count` SHALL equal `3`

#### Scenario: AX fingerprint is independent of class and DOM path for the same chosen section

- **GIVEN** two pages each containing three `<button>Save</button>` elements in three sections; the first page's "Settings" section has a `class` attribute `"panel"` and is the second sibling, the second page's "Settings" section has `class` attribute `"sidebar-card"` and is the first sibling
- **AND** a stub `llm_chat` that returns `{"index": K}` where K is the index of the "Settings" candidate on each page (which differs across the two pages, but resolves to the same section heading)
- **WHEN** a caller invokes `locate_l3(page, role="button", name="Save", llm_chat=stub)` against each page
- **THEN** the two `LocateResult.ax_fingerprint` values SHALL be equal

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

### Requirement: Module-local locator exception types

The system SHALL define `LocateError`, `LocatorMiss`, and `IntentParseError` as exception classes in `agent.locate`. `LocatorMiss` and `IntentParseError` SHALL each be subclasses of `LocateError`. `LocatorMiss` SHALL carry a `reason` attribute restricted to `"zero_matches"`, `"ambiguous"`, or `"vision_miss"`, and SHALL carry an integer `match_count` attribute (zero for `"zero_matches"` and `"vision_miss"`, the actual count for `"ambiguous"`). These types SHALL be importable directly from `agent.locate` so callers can catch them by type rather than parsing message strings.

#### Scenario: Exception types are importable and form a hierarchy

- **WHEN** a caller executes `from agent.locate import LocateError, LocatorMiss, IntentParseError`
- **THEN** the import SHALL succeed
- **AND** `LocatorMiss` and `IntentParseError` SHALL each be subclasses of `LocateError`

#### Scenario: LocatorMiss reason is constrained

- **WHEN** code constructs `LocatorMiss(reason="zero_matches", match_count=0)`
- **THEN** the construction SHALL succeed
- **AND** `miss.reason` SHALL equal `"zero_matches"`
- **AND** `miss.match_count` SHALL equal `0`

#### Scenario: LocatorMiss accepts vision_miss reason

- **WHEN** code constructs `LocatorMiss(reason="vision_miss", match_count=0)`
- **THEN** the construction SHALL succeed
- **AND** `miss.reason` SHALL equal `"vision_miss"`
- **AND** `miss.match_count` SHALL equal `0`

#### Scenario: LocatorMiss rejects unknown reasons

- **WHEN** code constructs `LocatorMiss(reason="something_else", match_count=0)`
- **THEN** the construction SHALL raise `ValueError`

### Requirement: L4 vision-fallback resolution

The system SHALL provide `agent.locate.locate_l4(page, *, role, name, intent, llm_chat=None) -> LocateResult` that resolves an element by capturing a viewport screenshot, asking a vision-capable LLM to return a bounding box around the target, and returning a coordinate target rather than a DOM selector.

`locate_l4` SHALL:

1. Read the viewport size via `page.viewport_size`. If `viewport_size` is `None`, `locate_l4` SHALL raise `LocatorMiss(reason="vision_miss", match_count=0)` immediately, without invoking the LLM or capturing a screenshot.
2. Capture a viewport screenshot via `page.screenshot(full_page=False)` returning raw PNG bytes.
3. Encode the PNG bytes as a `data:image/png;base64,<b64>` URL via stdlib `base64.b64encode`.
4. Resolve the LLM callable: `chat_fn = llm_chat if llm_chat is not None else _resolve_default_llm_chat()`. The default-resolver SHALL import `agent.llm.chat` lazily so module load of `agent.locate` does not pull in `agent.llm` / `httpx`.
5. Build a two-message OpenAI-compatible chat-completions `messages` list:
   - A `system` message instructing strict JSON-only reply of the form `{"bbox": [x, y, w, h]}` where `x,y` is the top-left corner in pixels (relative to the screenshot) and `w,h` are the width and height in pixels; no code fences, no prose.
   - A `user` message whose `content` is a 2-element list: a `{"type": "text", "text": ...}` part containing the intent (e.g. `"Submit button"`) and the viewport size, and a `{"type": "image_url", "image_url": {"url": "data:image/png;base64,<b64>"}}` part.
6. Invoke `chat_fn(messages=messages, temperature=0.0)`. If the call raises `LLMError` (any kind: transport, http, decode, config), `locate_l4` SHALL raise `LocatorMiss(reason="vision_miss", match_count=0)` with the original error chained via `raise ... from`.
7. Parse the response:
   - `response.content` MUST `json.loads` to a `dict`.
   - The dict MUST have a `bbox` key whose value is a `list` (or `tuple`) of exactly 4 numeric items.
   - Each item MUST be a finite number (`int` or `float`, not `bool`, not `NaN`, not `inf`).
   - Each item is normalized to `int` via `int(round(v))`.
   - The resulting `(x, y, w, h)` MUST satisfy `x >= 0`, `y >= 0`, `w > 0`, `h > 0`, `x + w <= viewport_w`, `y + h <= viewport_h`.
   - Any failure SHALL raise `LocatorMiss(reason="vision_miss", match_count=0)`.
8. Compute the click target: `cx = x + w // 2`, `cy = y + h // 2`.
9. Return `LocateResult(tier="L4_vision", role=role, name=name, selector="", ax_fingerprint=sha256(f"vision:{intent}:{cx}:{cy}".encode()).hexdigest(), confidence=0.5, coords=(cx, cy))`.

`locate_l4` SHALL NOT be invoked by L1, L2, or L3; it is reachable directly or via `locate()`'s last-tier cascade.

#### Scenario: Vision LLM returns valid bbox; click center is computed and returned

- **GIVEN** a page exposing a target element rendered as a bare `<div>` with no role, no accessible name, no label, and no placeholder
- **AND** the target is painted at viewport pixel rect `(100, 200, 80, 40)` (x, y, w, h)
- **AND** a stub `llm_chat` that returns a `ChatResponse` whose `content` is exactly the JSON string `{"bbox": [100, 200, 80, 40]}`
- **WHEN** a caller invokes `locate_l4(page, role="button", name=None, intent="Submit button", llm_chat=stub)`
- **THEN** the call SHALL return a `LocateResult` with `tier == "L4_vision"`
- **AND** `result.confidence` SHALL equal `0.5`
- **AND** `result.coords` SHALL equal `(140, 220)`
- **AND** `result.selector` SHALL equal `""`
- **AND** `result.ax_fingerprint` SHALL be a non-empty string

#### Scenario: Malformed JSON reply raises vision_miss

- **GIVEN** a page with the same target as above
- **AND** a stub `llm_chat` that returns a `ChatResponse` whose `content` is the string `not even close to JSON`
- **WHEN** a caller invokes `locate_l4(page, role="button", name=None, intent="Submit button", llm_chat=stub)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"vision_miss"`
- **AND** `LocatorMiss.match_count` SHALL equal `0`

#### Scenario: Missing bbox field raises vision_miss

- **GIVEN** a page with a target
- **AND** a stub `llm_chat` returning `{"box": [10, 20, 30, 40]}` (wrong key name)
- **WHEN** a caller invokes `locate_l4(page, role="button", name=None, intent="Submit button", llm_chat=stub)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"vision_miss"`

#### Scenario: Bbox with non-positive dimensions raises vision_miss

- **GIVEN** a page with a target
- **AND** a stub `llm_chat` returning `{"bbox": [10, 20, 0, 40]}` (zero width)
- **WHEN** a caller invokes `locate_l4(page, role="button", name=None, intent="Submit button", llm_chat=stub)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"vision_miss"`

#### Scenario: Bbox out of viewport bounds raises vision_miss

- **GIVEN** a page with viewport `1280×800`
- **AND** a stub `llm_chat` returning `{"bbox": [1200, 750, 200, 200]}` (extends past right and bottom edges)
- **WHEN** a caller invokes `locate_l4(page, role="button", name=None, intent="Submit button", llm_chat=stub)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"vision_miss"`

#### Scenario: Negative bbox origin raises vision_miss

- **GIVEN** a page with a target
- **AND** a stub `llm_chat` returning `{"bbox": [-10, 20, 30, 40]}` (negative x)
- **WHEN** a caller invokes `locate_l4(page, role="button", name=None, intent="Submit button", llm_chat=stub)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"vision_miss"`

#### Scenario: Bbox with wrong arity raises vision_miss

- **GIVEN** a page with a target
- **AND** a stub `llm_chat` returning `{"bbox": [10, 20, 30]}` (only 3 numbers)
- **WHEN** a caller invokes `locate_l4(page, role="button", name=None, intent="Submit button", llm_chat=stub)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"vision_miss"`

#### Scenario: Float bbox coordinates are accepted and rounded

- **GIVEN** a page with a target painted at `(100, 200, 80, 40)`
- **AND** a stub `llm_chat` returning `{"bbox": [99.6, 200.4, 80.0, 40.0]}`
- **WHEN** a caller invokes `locate_l4(page, role="button", name=None, intent="Submit button", llm_chat=stub)`
- **THEN** the call SHALL return a `LocateResult` with `tier == "L4_vision"`
- **AND** `result.coords` SHALL equal `(140, 220)`

#### Scenario: LLM transport error is mapped to vision_miss

- **GIVEN** a page with a target
- **AND** a stub `llm_chat` that raises `agent.llm.LLMError("transport boom", kind="transport")` when invoked
- **WHEN** a caller invokes `locate_l4(page, role="button", name=None, intent="Submit button", llm_chat=stub)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"vision_miss"`
- **AND** the chained cause (`__cause__`) SHALL be the original `LLMError`

#### Scenario: Vision prompt carries the screenshot as a base64 data URL

- **GIVEN** a page with a target, viewport size known
- **AND** a recording stub `llm_chat` that captures the `messages` argument and returns a valid bbox
- **WHEN** a caller invokes `locate_l4(page, role="button", name=None, intent="Submit button", llm_chat=stub)`
- **THEN** the captured `messages` SHALL be a list of length `2`
- **AND** the first message SHALL have `role == "system"` and its `content` SHALL contain the substring `"bbox"`
- **AND** the second message SHALL have `role == "user"` and its `content` SHALL be a list
- **AND** that list SHALL contain exactly one element with `type == "text"` whose `text` contains the intent string `"Submit button"`
- **AND** that list SHALL contain exactly one element with `type == "image_url"` whose `image_url.url` starts with the prefix `"data:image/png;base64,"`

#### Scenario: AX fingerprint is deterministic for the same intent and click center

- **GIVEN** two runs of `locate_l4` against pages that produce the same intent and the same `(cx, cy)` click center
- **WHEN** both runs return successfully
- **THEN** the two `LocateResult.ax_fingerprint` values SHALL be equal

#### Scenario: AX fingerprint changes when click center changes

- **GIVEN** two runs of `locate_l4` with the same intent but different validated bbox centers
- **WHEN** both runs return successfully
- **THEN** the two `LocateResult.ax_fingerprint` values SHALL differ

### Requirement: `LocateResult.coords` carries L4 click target

The system SHALL extend `agent.locate.LocateResult` with an optional `coords: tuple[int, int] | None = None` field. For results produced by L1, L2, and L3, `coords` SHALL be `None`. For results produced by L4, `coords` SHALL be the `(cx, cy)` viewport pixel pair at the bbox center, and `selector` SHALL be the empty string `""`. Consumers of `LocateResult` SHALL discriminate between selector-based and coordinate-based targets by inspecting `result.coords is not None` (equivalently `result.tier == "L4_vision"`).

#### Scenario: L1/L2/L3 results have coords=None

- **WHEN** a caller obtains a `LocateResult` from `locate_l1`, `locate_l2`, or `locate_l3`
- **THEN** `result.coords` SHALL be `None`
- **AND** `result.selector` SHALL be a non-empty Playwright-locatable selector string

#### Scenario: L4 result has coords populated and empty selector

- **WHEN** a caller obtains a `LocateResult` from `locate_l4`
- **THEN** `result.coords` SHALL be a 2-tuple of integers
- **AND** `result.selector` SHALL equal `""`
- **AND** `result.tier` SHALL equal `"L4_vision"`

### Requirement: Vision LLM honors `LLM_BASE_URL`

When `locate_l4` is invoked without an `llm_chat` argument, it SHALL resolve the default `agent.llm.chat` callable lazily. The resolved callable SHALL post to the OpenAI-compatible chat-completions endpoint at the URL determined by `agent.llm`'s base-URL precedence: an explicit `base_url` argument, then the `LLM_BASE_URL` environment variable, then the module default `http://localhost:8090`. No alternative endpoint, no provider-specific URL, and no hardcoded host SHALL be used by the L4 path.

#### Scenario: Default L4 client posts to LLM_BASE_URL when set

- **GIVEN** the `LLM_BASE_URL` environment variable is set to `"http://vision.example.test"`
- **AND** the HTTP transport of `agent.llm` is mocked to capture outbound requests
- **WHEN** `locate_l4` is invoked with `llm_chat=None` (resolving the default)
- **THEN** the captured outbound request URL SHALL begin with `"http://vision.example.test/v1/chat/completions"`

#### Scenario: Default L4 client falls back to module default when LLM_BASE_URL unset

- **GIVEN** the `LLM_BASE_URL` environment variable is unset
- **AND** the HTTP transport of `agent.llm` is mocked to capture outbound requests
- **WHEN** `locate_l4` is invoked with `llm_chat=None`
- **THEN** the captured outbound request URL SHALL begin with `"http://localhost:8090/v1/chat/completions"`

