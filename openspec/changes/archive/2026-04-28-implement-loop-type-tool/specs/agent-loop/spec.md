## MODIFIED Requirements

### Requirement: LLM tool surface exposed by the loop

The loop SHALL expose the following tools to the LLM via `tools` in every `llm_client.chat()` call:

- `goto(url: str)` — navigate the browser to the given URL.
- `read(intent?: str)` — read visible text from the page. If `intent` is provided, the loop SHALL attempt to resolve it via `locate_l1(page, ...)` first. If `locate_l1` raises `LocatorMiss(reason="zero_matches")`, the loop SHALL invoke the `Supervisor` to get an escalation decision. If the supervisor prescribes a next tier (e.g. `"L2_dom"`), the loop SHALL retry resolution at that tier (e.g. via `locate_l2`). If resolution ultimately succeeds, the loop SHALL read the element's text via `Browser.read(selector)` and return it as the tool result. If resolution fails at all tiers, or if the intent text cannot be parsed (`IntentParseError`), the loop SHALL return an error string as the tool result and continue (SHALL NOT terminate the run). If `intent` is absent or empty, the loop SHALL return the full page body text (up to 2000 characters of `document.body.innerText`).
- `click(intent: str)` — click a page element described by `intent`. The loop SHALL resolve the element via `_locate_with_supervisor` (same ladder and cache path used by `read`). On successful resolution the loop SHALL call `Locator.click(timeout=…)` on the resolved Playwright Locator. After the click the loop SHALL emit an `ActEvent` with `outcome` in `{ok, no_effect, nav, timeout, error}`. On `LocatorMiss` from `_locate_with_supervisor` (all tiers exhausted), the loop SHALL return an error string and continue (SHALL NOT terminate the run).
- `type(intent: str, text: str)` — fill a textbox described by `intent` with `text`. The loop SHALL resolve the element via `_locate_with_supervisor` (same ladder and cache path used by `read` and `click`). For textbox-role intents, `locate_l2` falls back to `get_by_placeholder`, enabling L2 escalation to succeed where L1 misses on placeholder-only inputs. On successful resolution the loop SHALL call `Locator.fill(text, timeout=5000)` on the resolved Playwright Locator. After the fill the loop SHALL emit an `ActEvent` with `outcome` in `{ok, timeout, error}`:
  - `outcome="ok"` — fill completed without error.
  - `outcome="timeout"` — the Playwright `TimeoutError` was raised during the fill.
  - `outcome="error"` — any other `PlaywrightError` was raised during the fill (e.g. element is not editable).
  - `ActEvent.diff` SHALL be set to `{}` (screenshot-diff deferred to a future ticket).
  - On `LocatorMiss` from `_locate_with_supervisor` (all tiers exhausted), the loop SHALL return an error string as the tool result and continue (SHALL NOT terminate the run).
- `done(result: object, evidence: {url: str, text_snippet: str})` — terminal tool: mark the task complete. The loop SHALL validate the evidence and exit with either `RunResult(status="succeeded", ...)` or `RunResult(status="unverified", ...)` depending on the validation result.
- `fail(reason: str)` — terminal tool: mark the task failed. The loop SHALL exit with `RunResult(status="failed", result=None, evidence=None, verifier=None)`.

The loop SHALL NOT expose `select`, `wait_for`, `back`, or `screenshot` in this ticket; those are added when tests demand them.

The `TOOLS` list SHALL include a `type` entry with function name `"type"` and required `intent` and `text` parameters, both of type `string`.

#### Scenario: TOOLS list includes type entry with intent and text parameters

- **WHEN** `agent.loop.TOOLS` is inspected
- **THEN** it SHALL contain an entry with `function.name == "type"`
- **AND** the entry's `parameters.properties` SHALL include `"intent"` with `type == "string"`
- **AND** the entry's `parameters.properties` SHALL include `"text"` with `type == "string"`
- **AND** both `"intent"` and `"text"` SHALL appear in the `parameters.required` list

#### Scenario: LLM calls type on a textbox — ActEvent outcome=ok emitted, run succeeds

- **GIVEN** a fixture page with `<input type="text" placeholder="Email">` and a stub LLM that emits `type(intent="Email textbox", text="hello@example.com")` on step 1 and `done(...)` on step 2
- **WHEN** the loop dispatches the type tool call and the textbox is located successfully
- **THEN** `Locator.fill("hello@example.com", timeout=5000)` SHALL be called on the resolved locator
- **AND** an `ActEvent` SHALL be emitted with `outcome="ok"`, `tool="type"`, and `args={"intent": "Email textbox", "text": "hello@example.com"}`
- **AND** the loop SHALL reach `done` and return `RunResult(status="succeeded")`

#### Scenario: LLM calls type on non-existent intent — tool error returned, loop continues

- **GIVEN** a fixture page with no matching textbox element (all tiers miss for the given intent)
- **AND** a stub LLM that emits `type(intent="Nonexistent textbox", text="foo")`
- **WHEN** the loop dispatches the type tool call and `_locate_with_supervisor` exhausts all tiers
- **THEN** the tool result SHALL be a string starting with `"Error:"`
- **AND** the loop SHALL NOT terminate; it SHALL append the error string as a tool result and continue to the next iteration

#### Scenario: LLM calls type and Locator.fill raises TimeoutError — ActEvent outcome=timeout

- **GIVEN** a fill whose target is unresponsive within the 5s timeout
- **WHEN** the loop dispatches type and `Locator.fill(text, timeout=5000)` raises `playwright.sync_api.TimeoutError`
- **THEN** an `ActEvent` SHALL be emitted with `outcome="timeout"`
- **AND** the tool result SHALL be a string starting with `"Error: type timeout"`
- **AND** the loop SHALL continue (SHALL NOT terminate the run)

#### Scenario: LLM calls type and Locator.fill raises a generic PlaywrightError — ActEvent outcome=error

- **GIVEN** a fill whose target element is not editable (e.g. raises `"element is not an HTMLInputElement"`)
- **WHEN** the loop dispatches type and `Locator.fill(text, timeout=5000)` raises `playwright.sync_api.Error`
- **THEN** an `ActEvent` SHALL be emitted with `outcome="error"`
- **AND** the tool result SHALL be a string starting with `"Error: type error"`
- **AND** the loop SHALL continue (SHALL NOT terminate the run)

## ADDED Requirements

### Requirement: type tool dispatch in loop

The loop SHALL handle `tool_call.name == "type"` in `_dispatch`. The dispatch contract is:

1. Extract `intent` and `text` from `args`. If either is absent or not a non-empty string, return an error string immediately (do NOT call locate).
2. Call `_locate_or_error_msg(page, intent, supervisor, cache=locator_cache, trace_writer=trace_writer, run_id=run_id, step_id=step_id)` to resolve the element. If locate returns an error string, return it and continue.
3. Record `t_fill = time.monotonic()`.
4. Call `page.locator(result.selector).fill(text, timeout=5000)`.
5. If fill succeeds → `outcome="ok"`.
6. If `playwright.sync_api.TimeoutError` raised → `outcome="timeout"`.
7. If any other `playwright.sync_api.Error` raised → `outcome="error"`.
8. Compute `elapsed_ms = int((time.monotonic() - t_fill) * 1000)`.
9. Emit `ActEvent(tool="type", args={"intent": intent, "text": text}, outcome=outcome, diff={}, ms=elapsed_ms)`.
10. Return `f"Typed into {intent!r} (ok)"` on success or `f"Error: type {outcome} for intent {intent!r}"` on failure.

The `ToolName` literal in `loop.py` SHALL be updated to include `"type"`.

Note: `ActEvent.tool` is typed as `str` in `agent/trace.py` — no schema change to `trace.py` is required.

#### Scenario: type dispatch returns ok string when textbox found and filled

- **GIVEN** a page with `<input type="text" placeholder="Email">` that `_locate_with_supervisor` resolves at L1 or L2
- **WHEN** `_dispatch("type", {"intent": "Email textbox", "text": "hello@example.com"}, browser, supervisor, ...)` is called
- **THEN** it SHALL return a non-error string (not starting with `"Error:"`)
- **AND** an `ActEvent` with `outcome="ok"` and `tool="type"` SHALL be emitted

#### Scenario: type dispatch returns error string on LocatorMiss — loop continues

- **GIVEN** a page with no matching textbox (all tiers miss)
- **WHEN** `_dispatch("type", {"intent": "Nonexistent textbox", "text": "foo"}, browser, supervisor, ...)` is called
- **THEN** it SHALL return a string starting with `"Error:"`
- **AND** the loop SHALL NOT terminate; it SHALL append the error string as a tool result and continue to the next iteration
