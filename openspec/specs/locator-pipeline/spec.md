# locator-pipeline Specification

## Purpose
TBD - created by archiving change implement-locate-l1. Update Purpose after archive.
## Requirements
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

### Requirement: Intent parser

The system SHALL provide `agent.locate.parse_intent(intent: str) -> tuple[str, str | None]` that turns a natural-language intent into `(role, name)`. The parser SHALL strip a single leading article (`the`, `a`, `an`, case-insensitive) if present, then treat the final whitespace-separated token as the role and the remaining tokens (joined by single spaces) as the accessible name. If no leading text remains, the name SHALL be `None`. The role token SHALL be lowercased and validated against the supported role set: `button`, `link`, `textbox`, `checkbox`, `heading`. Unknown roles SHALL raise `IntentParseError`. Empty or whitespace-only intents SHALL raise `IntentParseError`.

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

The system SHALL define `agent.locate.LocateResult` as a dataclass with the fields `tier: str`, `role: str`, `name: str | None`, `selector: str`, `ax_fingerprint: str`, and `confidence: float`. This shape SHALL be the contract between the locator pipeline and its consumers (the agent loop, the supervisor, the locator cache, the trace writer); later tiers SHALL populate the same fields.

#### Scenario: Result is constructible and round-trippable through Playwright

- **GIVEN** a `LocateResult` returned by `locate_l1` for a unique button
- **WHEN** a caller invokes `page.locator(result.selector)`
- **THEN** the resulting Playwright `Locator` SHALL refer to the same DOM element that produced the result

#### Scenario: AX fingerprint is deterministic for the same role+name

- **WHEN** two `LocateResult`s are produced by L1 for the same `(role, name)` pair against accessibility nodes that share the same role and accessible name
- **THEN** their `ax_fingerprint` values SHALL be equal

### Requirement: Module-local locator exception types

The system SHALL define `LocateError`, `LocatorMiss`, and `IntentParseError` as exception classes in `agent.locate`. `LocatorMiss` and `IntentParseError` SHALL each be subclasses of `LocateError`. `LocatorMiss` SHALL carry a `reason` attribute restricted to `"zero_matches"` or `"ambiguous"`, and SHALL carry an integer `match_count` attribute (zero for `"zero_matches"`, the actual count for `"ambiguous"`). These types SHALL be importable directly from `agent.locate` so callers can catch them by type rather than parsing message strings.

#### Scenario: Exception types are importable and form a hierarchy

- **WHEN** a caller executes `from agent.locate import LocateError, LocatorMiss, IntentParseError`
- **THEN** the import SHALL succeed
- **AND** `LocatorMiss` and `IntentParseError` SHALL each be subclasses of `LocateError`

#### Scenario: LocatorMiss reason is constrained

- **WHEN** code constructs `LocatorMiss(reason="zero_matches", match_count=0)`
- **THEN** the construction SHALL succeed
- **AND** `miss.reason` SHALL equal `"zero_matches"`
- **AND** `miss.match_count` SHALL equal `0`

#### Scenario: LocatorMiss rejects unknown reasons

- **WHEN** code constructs `LocatorMiss(reason="something_else", match_count=0)`
- **THEN** the construction SHALL raise `ValueError`
