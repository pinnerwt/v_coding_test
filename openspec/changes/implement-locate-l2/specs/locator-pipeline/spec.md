## ADDED Requirements

### Requirement: L2 DOM-heuristic resolution

The system SHALL provide `agent.locate.locate_l2(page, *, role, name) -> LocateResult` that resolves an element via DOM heuristics, intended to catch the cases L1 misses (elements with no accessible name). `locate_l2` SHALL run an ordered list of strategies and return the first strategy that yields exactly one matching element. When no strategy yields a match, `locate_l2` SHALL raise `LocatorMiss(reason="zero_matches", match_count=0)`. When at least one strategy yields more than one match and no strategy yields exactly one, `locate_l2` SHALL raise `LocatorMiss(reason="ambiguous", match_count=N)` where `N` is the count from the first non-empty strategy. `locate_l2` SHALL NOT pick arbitrarily.

The supported strategies, in this order:

1. **Placeholder strategy** — only for `role == "textbox"` and only when `name` is non-empty. Uses Playwright's placeholder query (`page.get_by_placeholder(name, exact=False)`).
2. **Text-contains over a clickable taxonomy** — only for `role` in `{"button", "link"}` and only when `name` is non-empty. Restricts the candidate set to a per-role CSS taxonomy that includes non-semantic clickables (for `button`: `button, input[type=button], input[type=submit], input[type=reset], [role=button], [onclick], [class*="btn"], [class*="button"]`; for `link`: `a[href], [role=link]`), then filters by visible text via `Locator.filter(has_text=name)`.

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

#### Scenario: Ambiguous L2 raises with the first non-empty strategy's count

- **GIVEN** a page containing two `<div class="btn">Save</div>` elements in distinct sections and no other elements matching the `button` taxonomy with text `"Save"`
- **WHEN** a caller invokes `locate_l2(page, role="button", name="Save")`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"ambiguous"`
- **AND** `LocatorMiss.match_count` SHALL equal `2`

#### Scenario: All strategies miss raises zero_matches

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

## MODIFIED Requirements

### Requirement: Locator pipeline entry point

The system SHALL expose `agent.locate.locate(page, intent)` as the single entry point for resolving a natural-language intent to a unique element on the currently loaded Playwright page. `locate` SHALL parse the intent into `(role, name)` and call `locate_l1`. If `locate_l1` raises `LocatorMiss(reason="zero_matches")`, `locate` SHALL fall through to `locate_l2(page, role=role, name=name)` and return its result (or propagate its `LocatorMiss`). If `locate_l1` raises `LocatorMiss(reason="ambiguous")`, `locate` SHALL re-raise that exception unchanged so a later tier (L3 semantic rerank) can claim it. Later tiers (L3 rerank, L4 vision) extend the same entry point without changing its signature. On success `locate` SHALL return a `LocateResult`. On failure it SHALL raise either `LocatorMiss` (UI-state failure — element absent or ambiguous after all wired-in tiers) or `IntentParseError` (the intent itself could not be parsed).

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

#### Scenario: Does not fall through to L2 on L1 ambiguous

- **GIVEN** a page where two accessible buttons share the name `Save` (L1 returns `LocatorMiss(reason="ambiguous", match_count=2)`)
- **WHEN** a caller invokes `locate(page, "Save button")`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"ambiguous"`
- **AND** `LocatorMiss.match_count` SHALL equal `2`

#### Scenario: Surfaces unparseable intent

- **WHEN** a caller invokes `locate(page, "do the thing")` with no recognised trailing role keyword
- **THEN** the call SHALL raise `IntentParseError`
- **AND** the exception message SHALL include the offending intent string

#### Scenario: Surfaces L2 zero-matches when both tiers miss

- **GIVEN** a page that exposes no element resolvable by L1 or by any L2 strategy for a given intent
- **WHEN** a caller invokes `locate(page, intent)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"zero_matches"`
