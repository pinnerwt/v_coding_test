## MODIFIED Requirements

### Requirement: click tool dispatch in loop

The loop SHALL handle `tool_call.name == "click"` in `_dispatch`. The dispatch contract is:

1. Call `_locate_with_supervisor(page, intent, supervisor, cache=locator_cache, trace_writer=trace_writer, run_id=run_id, step_id=step_id)` to resolve the element.
2. Record `url_before = page.url`.
3. Call `page.locator(result.selector).click(timeout=5000)`.
4. If click succeeds: compare `page.url` to `url_before`. If changed → `outcome="nav"`, else → `outcome="ok"`.
5. If `playwright.sync_api.TimeoutError` raised (capture as `exc`) → `outcome="timeout"`.
6. If any other `playwright.sync_api.Error` raised (capture as `exc`) → `outcome="error"`.
7. Emit `ActEvent(tool="click", args={"intent": intent}, outcome=<outcome>, diff=<diff>, ms=<elapsed_ms>)`. The `diff` SHALL be `{}` when `outcome` is `"ok"` or `"nav"`, and `{"error": f"{exc.__class__.__name__}: {exc}"}` when `outcome` is `"timeout"` or `"error"`.
8. Return a string summarising the outcome to the LLM (e.g. `"Clicked 'Submit button' (ok)"` or `"Error: click timeout for intent 'Submit button'"`).
9. On `LocatorMiss` from `_locate_with_supervisor` (all tiers exhausted): return an error string and continue (do NOT terminate the run).

The `ToolName` literal in `loop.py` SHALL be updated to include `"click"`.

#### Scenario: click dispatch returns ok string when element found and clicked

- **GIVEN** a page with a `<button>Submit</button>` element that L1 locates successfully
- **WHEN** `_dispatch("click", {"intent": "Submit button"}, browser, supervisor, ...)` is called
- **THEN** it SHALL return a non-error string (not starting with `"Error:"`)
- **AND** an `ActEvent` with `outcome="ok"` and `diff={}` SHALL be emitted

#### Scenario: click dispatch returns error string on LocatorMiss — loop continues

- **GIVEN** a page with no button element (all tiers miss)
- **WHEN** `_dispatch("click", {"intent": "Nonexistent button"}, browser, supervisor, ...)` is called
- **THEN** it SHALL return a string starting with `"Error:"`
- **AND** the loop SHALL NOT terminate; it SHALL append the error string as a tool result and continue to the next iteration

#### Scenario: click dispatch surfaces playwright exception class+message in ActEvent.diff on timeout

- **GIVEN** a page where the located element raises `playwright.sync_api.TimeoutError("Locator.click: Timeout 5000ms exceeded.")` when clicked
- **WHEN** `_dispatch("click", {"intent": "Submit button"}, browser, supervisor, ...)` is called
- **THEN** the emitted `ActEvent` SHALL have `outcome="timeout"`
- **AND** `ActEvent.diff` SHALL equal `{"error": "TimeoutError: Locator.click: Timeout 5000ms exceeded."}` (the exception class name followed by `": "` followed by the exception's `str()` form)

#### Scenario: click dispatch surfaces playwright exception class+message in ActEvent.diff on error

- **GIVEN** a page where the located element raises `playwright.sync_api.Error("Element is not attached to the DOM")` when clicked
- **WHEN** `_dispatch("click", {"intent": "Submit button"}, browser, supervisor, ...)` is called
- **THEN** the emitted `ActEvent` SHALL have `outcome="error"`
- **AND** `ActEvent.diff["error"]` SHALL be a non-empty string of the form `"<exception_class_name>: <message>"` where `<exception_class_name>` equals the raised exception's `__class__.__name__` and `<message>` contains `"Element is not attached to the DOM"`

### Requirement: type tool dispatch in loop

The loop SHALL handle `tool_call.name == "type"` in `_dispatch`. The dispatch contract is:

1. Extract `intent` and `text` from `args`. If either is absent or not a non-empty string, return an error string immediately (do NOT call locate).
2. Call `_locate_or_error_msg(page, intent, supervisor, cache=locator_cache, trace_writer=trace_writer, run_id=run_id, step_id=step_id)` to resolve the element. If locate returns an error string, return it and continue.
3. Record `t_fill = time.monotonic()`.
4. Call `page.locator(result.selector).fill(text, timeout=5000)`.
5. If fill succeeds → `outcome="ok"`.
6. If `playwright.sync_api.TimeoutError` raised (capture as `exc`) → `outcome="timeout"`.
7. If any other `playwright.sync_api.Error` raised (capture as `exc`) → `outcome="error"`.
8. Compute `elapsed_ms = int((time.monotonic() - t_fill) * 1000)`.
9. Emit `ActEvent(tool="type", args={"intent": intent, "text": text}, outcome=outcome, diff=<diff>, ms=elapsed_ms)`. The `diff` SHALL be `{}` when `outcome` is `"ok"`, and `{"error": f"{exc.__class__.__name__}: {exc}"}` when `outcome` is `"timeout"` or `"error"`.
10. Return `f"Typed into {intent!r} (ok)"` on success or `f"Error: type {outcome} for intent {intent!r}"` on failure.

The `ToolName` literal in `loop.py` SHALL be updated to include `"type"`.

Note: `ActEvent.tool` is typed as `str` in `agent/trace.py` — no schema change to `trace.py` is required.

#### Scenario: type dispatch returns ok string when textbox found and filled

- **GIVEN** a page with `<input type="text" placeholder="Email">` that `_locate_with_supervisor` resolves at L1 or L2
- **WHEN** `_dispatch("type", {"intent": "Email textbox", "text": "hello@example.com"}, browser, supervisor, ...)` is called
- **THEN** it SHALL return a non-error string (not starting with `"Error:"`)
- **AND** an `ActEvent` with `outcome="ok"`, `tool="type"`, and `diff={}` SHALL be emitted

#### Scenario: type dispatch returns error string on LocatorMiss — loop continues

- **GIVEN** a page with no matching textbox (all tiers miss)
- **WHEN** `_dispatch("type", {"intent": "Nonexistent textbox", "text": "foo"}, browser, supervisor, ...)` is called
- **THEN** it SHALL return a string starting with `"Error:"`
- **AND** the loop SHALL NOT terminate; it SHALL append the error string as a tool result and continue to the next iteration

#### Scenario: type dispatch surfaces playwright exception class+message in ActEvent.diff on timeout

- **GIVEN** a page where the located textbox raises `playwright.sync_api.TimeoutError("Locator.fill: Timeout 5000ms exceeded.")` when filled
- **WHEN** `_dispatch("type", {"intent": "Email textbox", "text": "hello@example.com"}, browser, supervisor, ...)` is called
- **THEN** the emitted `ActEvent` SHALL have `outcome="timeout"`
- **AND** `ActEvent.diff` SHALL equal `{"error": "TimeoutError: Locator.fill: Timeout 5000ms exceeded."}`
