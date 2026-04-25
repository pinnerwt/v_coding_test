## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: Locator pipeline entry point

The system SHALL expose `agent.locate.locate(page, intent, *, llm_chat=None)` as the single entry point for resolving a natural-language intent to a unique element on the currently loaded Playwright page. `locate` SHALL parse the intent into `(role, name)` and call `locate_l1`. If `locate_l1` raises `LocatorMiss(reason="zero_matches")`, `locate` SHALL fall through to `locate_l2(page, role=role, name=name)` and return its result (or propagate its `LocatorMiss`). If `locate_l1` raises `LocatorMiss(reason="ambiguous")`, `locate` SHALL fall through to `locate_l3(page, role=role, name=name, llm_chat=llm_chat)` and return its result (or propagate its `LocatorMiss`). Later tiers (L4 vision) extend the same entry point without changing its signature except to add further keyword arguments. The `llm_chat` parameter SHALL be forwarded to `locate_l3`; passing `None` (the default) means `locate_l3` will resolve the default `agent.llm.chat`. On success `locate` SHALL return a `LocateResult`. On failure it SHALL raise either `LocatorMiss` (UI-state failure — element absent or unresolvable after all wired-in tiers) or `IntentParseError` (the intent itself could not be parsed).

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
- **AND** `result.role` SHALL equal `"button"`
- **AND** `result.name` SHALL equal `"Save"`

#### Scenario: Surfaces unparseable intent

- **WHEN** a caller invokes `locate(page, "do the thing")` with no recognised trailing role keyword
- **THEN** the call SHALL raise `IntentParseError`
- **AND** the exception message SHALL include the offending intent string

#### Scenario: Surfaces L2 zero-matches when both L1 and L2 miss

- **GIVEN** a page that exposes no element resolvable by L1 or by any L2 strategy for a given intent
- **WHEN** a caller invokes `locate(page, intent)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"zero_matches"`

#### Scenario: Surfaces L3 ambiguous when LLM cannot disambiguate

- **GIVEN** a page where L1 returns ambiguous on a given intent
- **AND** a stub `llm_chat` returning a malformed JSON reply
- **WHEN** a caller invokes `locate(page, intent, llm_chat=stub)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"ambiguous"`
