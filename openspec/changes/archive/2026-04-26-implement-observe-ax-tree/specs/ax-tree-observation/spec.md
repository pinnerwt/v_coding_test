## ADDED Requirements

### Requirement: INTERACTABLE_ROLES constant

`agent.observe` SHALL export a module-level `frozenset` named `INTERACTABLE_ROLES` containing exactly the following lowercase role strings: `button`, `link`, `textbox`, `combobox`, `checkbox`, `radio`, `tab`, `menuitem`, `option`, `heading`. Tests SHALL import and reference this constant directly.

#### Scenario: INTERACTABLE_ROLES contains the canonical set

- **WHEN** `from agent.observe import INTERACTABLE_ROLES` is executed
- **THEN** `INTERACTABLE_ROLES` SHALL be a `frozenset`
- **AND** it SHALL contain exactly `{"button", "link", "textbox", "combobox", "checkbox", "radio", "tab", "menuitem", "option", "heading"}`

### Requirement: MAX_NODES and MAX_NAME_LEN constants

`agent.observe` SHALL export module-level integer constants `MAX_NODES` (default 200) and `MAX_NAME_LEN` (default 80). Both SHALL be importable by tests so tests can assert cap behavior without hardcoding values.

#### Scenario: Constants are importable and have expected defaults

- **WHEN** `from agent.observe import MAX_NODES, MAX_NAME_LEN` is executed
- **THEN** `MAX_NODES` SHALL equal `200`
- **AND** `MAX_NAME_LEN` SHALL equal `80`

### Requirement: build_observation function signature

`agent.observe` SHALL export a function `build_observation(browser, last_action)` that accepts a `Browser` instance and a `last_action` dict or `None`, and returns a `dict` with exactly these keys: `url` (str), `title` (str), `ax_tree_digest` (str), `ax_fingerprint` (str), `last_action` (dict or None).

#### Scenario: Return dict has required keys

- **WHEN** `build_observation(browser, None)` is called with a browser that has navigated to a page
- **THEN** the returned dict SHALL contain keys `url`, `title`, `ax_tree_digest`, `ax_fingerprint`, `last_action`
- **AND** `url` SHALL be a non-empty string matching the current page URL
- **AND** `title` SHALL be a string (may be empty if the page has no `<title>`)
- **AND** `ax_tree_digest` SHALL be a string
- **AND** `ax_fingerprint` SHALL be a 64-character lowercase hex string (SHA-256)
- **AND** `last_action` SHALL be `None`

#### Scenario: last_action is threaded through

- **WHEN** `build_observation(browser, {"tool": "goto", "intent": "navigate", "outcome": "ok"})` is called
- **THEN** the returned dict's `last_action` key SHALL equal `{"tool": "goto", "intent": "navigate", "outcome": "ok"}`

#### Scenario: Closed browser returns zero-observation dict

- **WHEN** `build_observation(browser, None)` is called and `browser._page` is `None`
- **THEN** the returned dict SHALL have `url == ""`, `title == ""`, `ax_tree_digest == ""`
- **AND** `ax_fingerprint` SHALL be the SHA-256 hex digest of an empty string (`"e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"`)
- **AND** `last_action` SHALL be `None`

### Requirement: AX tree filtering — interactable nodes and headings only

`build_observation` SHALL walk the Playwright accessibility snapshot tree and collect only nodes whose `role` appears in `INTERACTABLE_ROLES`. Nodes with roles not in that set SHALL be excluded from the digest. The walk SHALL be depth-first; the order of nodes in the output SHALL match DFS traversal order.

#### Scenario: Decorative divs excluded, buttons included

- **GIVEN** an HTML page with decorative `<div>` elements (role `generic`) and one `<button>Click me</button>`
- **WHEN** `build_observation(browser, None)` is called after navigating to that page
- **THEN** `ax_tree_digest` SHALL contain a line matching `[button] "Click me"`
- **AND** `ax_tree_digest` SHALL NOT contain any line with role `generic` or `div`

#### Scenario: Links and headings included

- **GIVEN** an HTML page with an `<h2>Section Title</h2>` and an `<a href="#">Read more</a>`
- **WHEN** `build_observation(browser, None)` is called after navigating to that page
- **THEN** `ax_tree_digest` SHALL contain a line matching `[heading` (with level) `] "Section Title"`
- **AND** `ax_tree_digest` SHALL contain a line matching `[link] "Read more"`

### Requirement: Serialization format — one node per line

Each collected node SHALL appear as one line in `ax_tree_digest` using the format `[role] "name"`. Heading nodes SHALL include their level as `[heading:N] "name"` where N is the heading level integer (1–6). If a node has no accessible name or an empty name, it SHALL appear as `[role] ""`. Lines SHALL be joined by newline characters (`\n`); no trailing newline.

#### Scenario: Format matches [role] "name" pattern

- **GIVEN** a page with `<button>Submit</button>` and `<input type="text" placeholder="Search">`
- **WHEN** `build_observation(browser, None)` is called
- **THEN** `ax_tree_digest` SHALL contain the line `[button] "Submit"`
- **AND** SHALL contain a line matching `[textbox] "Search"` (or `[textbox] ""` if placeholder is not surfaced as accessible name)

#### Scenario: Heading level is included in serialization

- **GIVEN** a page with `<h1>Main Title</h1>` and `<h3>Sub-section</h3>`
- **WHEN** `build_observation(browser, None)` is called
- **THEN** `ax_tree_digest` SHALL contain the line `[heading:1] "Main Title"`
- **AND** SHALL contain the line `[heading:3] "Sub-section"`

### Requirement: Node count cap — MAX_NODES

When the DFS walk finds more than `MAX_NODES` matching nodes, the walk SHALL stop collecting at `MAX_NODES` entries and append a sentinel line of the form `[... N more nodes truncated]` where N is the number of remaining matching nodes that were not collected. The sentinel line SHALL appear as the last line of `ax_tree_digest`.

#### Scenario: 1000-button page is capped at MAX_NODES

- **GIVEN** an HTML page with 1000 `<button>` elements
- **WHEN** `build_observation(browser, None)` is called
- **THEN** the number of `[button]` lines in `ax_tree_digest` SHALL equal `MAX_NODES`
- **AND** the last line of `ax_tree_digest` SHALL match the pattern `\[... \d+ more nodes truncated\]`
- **AND** `ax_tree_digest` SHALL NOT contain more than `MAX_NODES + 1` lines total (MAX_NODES node lines + 1 sentinel)

### Requirement: Accessible name length cap — MAX_NAME_LEN

If a node's accessible name exceeds `MAX_NAME_LEN` characters, the name SHALL be truncated to `MAX_NAME_LEN` characters and a `…` suffix appended. The total length of the quoted name in the serialization (including `…`) SHALL be `MAX_NAME_LEN + 1` characters.

#### Scenario: Long accessible name is truncated

- **GIVEN** a page with a `<button>` whose accessible name is a 200-character string
- **WHEN** `build_observation(browser, None)` is called
- **THEN** the button's name in `ax_tree_digest` SHALL be at most `MAX_NAME_LEN` characters followed by `…`

### Requirement: ax_fingerprint is SHA-256 of ax_tree_digest

`ax_fingerprint` SHALL equal `hashlib.sha256(ax_tree_digest.encode()).hexdigest()` — a 64-character lowercase hex string. Two observations with identical `ax_tree_digest` strings SHALL produce identical `ax_fingerprint` values. Two observations that differ in any node's role or name SHALL produce different `ax_fingerprint` values (with overwhelming probability).

#### Scenario: Fingerprint is deterministic

- **GIVEN** two calls to `build_observation(browser, None)` on the same page without any page changes in between
- **WHEN** both calls complete
- **THEN** both `ax_fingerprint` values SHALL be equal

#### Scenario: Fingerprint changes when page changes

- **GIVEN** a first call to `build_observation` producing `fp1`
- **AND** the page DOM is then modified to add a new `<button>`
- **WHEN** a second call to `build_observation` produces `fp2`
- **THEN** `fp1` SHALL NOT equal `fp2`

### Requirement: ax_tree_digest round-trips through trace.py JSON

`ObservationEvent.ax_tree_digest` in `agent.trace` is typed `str`. The string produced by `build_observation` SHALL survive JSON serialization via `ObservationEvent.model_dump_json()` and deserialization via `ObservationEvent.model_validate_json()` unchanged — i.e., the deserialized `ax_tree_digest` SHALL equal the original string character-for-character.

#### Scenario: ax_tree_digest survives ObservationEvent round-trip

- **GIVEN** an `ax_tree_digest` string produced by `build_observation`
- **WHEN** it is stored in an `ObservationEvent` and round-tripped through `model_dump_json()` → `model_validate_json()`
- **THEN** the deserialized `ax_tree_digest` SHALL equal the original string
- **AND** the deserialized `ax_fingerprint` SHALL equal the original fingerprint
