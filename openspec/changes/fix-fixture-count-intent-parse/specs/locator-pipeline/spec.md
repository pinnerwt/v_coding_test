## MODIFIED Requirements

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

#### Scenario: still-unknown role rejected

- **WHEN** a caller invokes `parse_intent("Submit widget")`
- **THEN** the call SHALL raise `IntentParseError`
- **AND** the exception message SHALL include the offending role token `"widget"`
