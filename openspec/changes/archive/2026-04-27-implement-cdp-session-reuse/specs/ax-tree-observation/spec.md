## MODIFIED Requirements

### Requirement: build_observation function signature

`agent.observe` SHALL export a function `build_observation(browser, last_action)` that accepts a `Browser` instance and a `last_action` dict or `None`, and returns a `dict` with exactly these keys: `url` (str), `title` (str), `ax_tree_digest` (str), `ax_fingerprint` (str), `last_action` (dict or None). The internal helper `_ax_nodes` SHALL accept the `Browser` instance (not the raw page) so it can access the CDP session cache.

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
