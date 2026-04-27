## ADDED Requirements

### Requirement: Browser holds a CDP session cache dict

`Browser.__init__` SHALL initialize an instance attribute `_cdp_sessions` as an empty `dict`. The dict SHALL be keyed by `id(page)` (Python object identity integer) and its values SHALL be `CDPSession` objects obtained from `page.context.new_cdp_session(page)`.

#### Scenario: _cdp_sessions initialized empty

- **WHEN** a `Browser` instance is created
- **THEN** `browser._cdp_sessions` SHALL be an empty `dict`

### Requirement: One CDP session opened per page lifetime

Across multiple `build_observation` calls on the same page object, `page.context.new_cdp_session` SHALL be called exactly once. Subsequent calls SHALL reuse the cached `CDPSession` without calling `new_cdp_session` again.

#### Scenario: N build_observation calls open only one CDP session

- **GIVEN** a `Browser` in `__enter__` context with a page loaded
- **WHEN** `build_observation` is called 10 times on the same browser
- **THEN** `page.context.new_cdp_session` SHALL have been called exactly once
- **AND** all 10 observations SHALL return non-empty `ax_tree_digest` values

### Requirement: Page navigation invalidates cached session

When `browser._page` is replaced with a new page object (a different Python object with a different `id`), any cached sessions keyed to the old page id SHALL be detached and removed from `_cdp_sessions` before a fresh session is opened for the new page.

#### Scenario: New page object triggers fresh CDP session

- **GIVEN** a `Browser` that has made at least one `build_observation` call (session cached for page A)
- **WHEN** the browser navigates to a new page causing `browser._page` to become a new object (page B)
- **AND** `build_observation` is called again
- **THEN** `page.context.new_cdp_session` SHALL be called a second time (for page B)
- **AND** `_cdp_sessions` SHALL contain only an entry for the new page's id

### Requirement: Browser.__exit__ detaches all cached sessions

On `Browser.__exit__`, every `CDPSession` in `_cdp_sessions` SHALL have `detach()` called on it. Individual `detach()` errors SHALL be caught and suppressed so teardown of the browser context still proceeds. After the loop `_cdp_sessions` SHALL be empty.

#### Scenario: __exit__ detaches all sessions without raising

- **GIVEN** a `Browser` that has a non-empty `_cdp_sessions` dict
- **WHEN** `Browser.__exit__` is called
- **THEN** the `with` block SHALL exit without raising any exception
- **AND** all cached sessions SHALL have had `detach()` called on them

#### Scenario: __exit__ suppresses detach errors

- **GIVEN** a `Browser` whose cached `CDPSession.detach()` raises an exception
- **WHEN** `Browser.__exit__` is called
- **THEN** no exception SHALL propagate from `__exit__`
- **AND** the browser context SHALL still be closed normally

### Requirement: Fallback when _cdp_sessions is absent

If the object passed to `_ax_nodes` does not have a `_cdp_sessions` attribute (e.g. a test double created with `types.SimpleNamespace`), `_ax_nodes` SHALL fall back to the direct per-call `new_cdp_session` / `detach` pattern. This preserves backward compatibility with existing test doubles.

#### Scenario: SimpleNamespace without _cdp_sessions uses per-call pattern

- **GIVEN** a fake browser object (`types.SimpleNamespace`) with no `_cdp_sessions` attribute
- **WHEN** `_ax_nodes` is called with that fake browser
- **THEN** `fake_context.new_cdp_session` SHALL be called directly
- **AND** the function SHALL return the AX nodes or an empty list on error, without raising `AttributeError`
