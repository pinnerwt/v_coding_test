## ADDED Requirements

### Requirement: Locator pipeline entry point

The system SHALL expose `agent.locate.locate(page, intent)` as the single entry point for resolving a natural-language intent to a unique element on the currently loaded Playwright page. In this change, `locate` SHALL run only the L1 (accessibility-tree) tier; later tiers (L2 DOM, L3 rerank, L4 vision) extend the same entry point without changing its signature. On success `locate` SHALL return a `LocateResult`. On failure it SHALL raise either `LocatorMiss` (UI-state failure — element absent or ambiguous) or `IntentParseError` (the intent itself could not be parsed).

#### Scenario: Resolves a parseable intent via L1

- **GIVEN** a page exposing exactly one accessible element matching role `button` and accessible name `Submit`
- **WHEN** a caller invokes `locate(page, "Submit button")`
- **THEN** the call SHALL return a `LocateResult`
- **AND** `result.tier` SHALL equal `"L1_ax"`
- **AND** `result.role` SHALL equal `"button"`
- **AND** `result.name` SHALL equal `"Submit"`

#### Scenario: Surfaces unparseable intent

- **WHEN** a caller invokes `locate(page, "do the thing")` with no recognised trailing role keyword
- **THEN** the call SHALL raise `IntentParseError`
- **AND** the exception message SHALL include the offending intent string

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
