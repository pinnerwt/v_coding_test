## MODIFIED Requirements

### Requirement: LLM tool surface exposed by the loop

The loop SHALL expose the following tools to the LLM via `tools` in every `llm_client.chat()` call:

- `goto(url: str)` — navigate the browser to the given URL.
- `read(intent?: str)` — read visible text from the page. If `intent` is provided, the loop SHALL attempt to resolve it via `locate_l1(page, ...)` first. If `locate_l1` raises `LocatorMiss(reason="zero_matches")`, the loop SHALL invoke the `Supervisor` to get an escalation decision. If the supervisor prescribes a next tier (e.g. `"L2_dom"`), the loop SHALL retry resolution at that tier (e.g. via `locate_l2`). If resolution ultimately succeeds, the loop SHALL read the element's text via `Browser.read(selector)` and return it as the tool result. If resolution fails at all tiers, the loop SHALL return an error string as the tool result and continue. If `intent` is absent or empty, the loop SHALL return the full page body text (up to 2000 characters of `document.body.innerText`).
- `click(intent: str)` — click a page element described by `intent`. The loop SHALL resolve the element via `_locate_with_supervisor` (same ladder and cache path used by `read`). On successful resolution the loop SHALL call `Locator.click(timeout=…)` on the resolved Playwright Locator. After the click the loop SHALL emit an `ActEvent` with `outcome` in `{ok, no_effect, nav, timeout, error}`:
  - `outcome="ok"` — click completed and the page URL did not change.
  - `outcome="nav"` — click completed and the page URL changed (same-tab navigation detected).
  - `outcome="timeout"` — the Playwright `TimeoutError` was raised during the click.
  - `outcome="error"` — any other `PlaywrightError` was raised during the click.
  - `outcome="no_effect"` — reserved for future use (not emitted by this implementation).
  - `ActEvent.diff` SHALL be set to `{}` (screenshot-diff deferred to a future ticket).
  - On `LocatorMiss(reason="zero_matches")` from L1, the loop SHALL surface the miss to the supervisor for L1→L2 escalation via the existing `_locate_with_supervisor` path. If escalation succeeds, the click is retried at the resolved tier. If all tiers are exhausted (supervisor returns `policy="halt"`), the loop SHALL return an error string as the tool result and continue (SHALL NOT terminate the run).
- `done(result: object, evidence: {url: str, text_snippet: str})` — terminal tool: mark the task complete. The loop SHALL validate the evidence and exit with either `RunResult(status="succeeded", ...)` or `RunResult(status="unverified", ...)` depending on the validation result.
- `fail(reason: str)` — terminal tool: mark the task failed. The loop SHALL exit with `RunResult(status="failed", result=None, evidence=None, verifier=None)`.

The loop SHALL NOT expose `type`, `select`, `wait_for`, `back`, or `screenshot` in this ticket; those are added when tests demand them.

The `TOOLS` list SHALL include a `click` entry with function name `"click"` and a required `intent` parameter of type `string`.

#### Scenario: TOOLS list includes click entry with intent parameter

- **WHEN** `agent.loop.TOOLS` is inspected
- **THEN** it SHALL contain an entry with `function.name == "click"`
- **AND** the entry's `parameters.properties` SHALL include `"intent"` with `type == "string"`
- **AND** `"intent"` SHALL appear in the `parameters.required` list

#### Scenario: LLM calls goto — browser navigates

- **GIVEN** the LLM emits a `goto` tool call with a valid URL
- **WHEN** the loop processes the tool call
- **THEN** the browser SHALL navigate to that URL (via `Browser.goto(url)`)
- **AND** the loop SHALL continue to the next iteration

#### Scenario: LLM calls read without intent — returns body text

- **GIVEN** the LLM emits a `read` tool call with no `intent` argument
- **WHEN** the loop processes the tool call
- **THEN** the loop SHALL evaluate `document.body.innerText` on the current page
- **AND** return up to 2000 characters of that text as the tool result
- **AND** continue to the next iteration

#### Scenario: LLM calls read with intent — uses locate to find element

- **GIVEN** the LLM emits a `read` tool call with `intent="the article heading"`
- **WHEN** the loop processes the tool call
- **THEN** the loop SHALL call `locate_l1(page, ...)` (or an equivalent locate call) to resolve the element
- **AND** read the element's text via `Browser.read(selector)` where `selector` is the result's selector
- **AND** return the text as the tool result
- **AND** continue to the next iteration

#### Scenario: LLM calls click on resolved element — ActEvent outcome=ok emitted

- **GIVEN** a fixture page with a single `<button>Submit</button>` element
- **AND** a stub LLM that emits `click(intent="Submit button")` on step 1 and `done(...)` on step 2
- **WHEN** the loop dispatches the click tool call and the button is located successfully at L1
- **THEN** `Locator.click(timeout=…)` SHALL be called on the resolved locator
- **AND** an `ActEvent` SHALL be emitted with `outcome="ok"`, `tool="click"`, and `args={"intent": "Submit button"}`
- **AND** the loop SHALL reach `done` and return `RunResult(status="succeeded")`

#### Scenario: LLM calls click and navigation occurs — ActEvent outcome=nav

- **GIVEN** a fixture page with a link-styled button that navigates to a second page when clicked
- **AND** a stub LLM that emits `click(intent="Go button")` on step 1 and `done(...)` on step 2
- **WHEN** the loop dispatches the click and the page URL changes after the click
- **THEN** an `ActEvent` SHALL be emitted with `outcome="nav"`
- **AND** the loop SHALL continue and reach `done`

#### Scenario: LLM calls click, L1 LocatorMiss triggers supervisor escalation to L2

- **GIVEN** a fixture page where the target button has no ARIA role (L1 returns `LocatorMiss(reason="zero_matches")`) but is detectable at L2
- **AND** a stub LLM that emits `click(intent="Submit button")`
- **WHEN** the loop dispatches the click and L1 raises `LocatorMiss(reason="zero_matches")`
- **THEN** the loop SHALL invoke `supervisor.handle(miss, current_tier="L1_ax")`
- **AND** the supervisor SHALL return `next_tier="L2_dom"`
- **AND** a `SupervisorEvent` with `policy="next_tier"` SHALL be emitted in the trace
- **AND** the loop SHALL proceed with `Locator.click` against the L2-resolved selector

#### Scenario: LLM calls click and Locator.click raises TimeoutError — ActEvent outcome=timeout

- **GIVEN** a click whose target is unclickable within the 5s timeout
- **WHEN** the loop dispatches click and `Locator.click(timeout=5000)` raises `playwright.sync_api.TimeoutError`
- **THEN** an `ActEvent` SHALL be emitted with `outcome="timeout"`
- **AND** the tool result SHALL be an error string starting with `"Error: click timeout"`
- **AND** the loop SHALL continue (SHALL NOT terminate the run)

#### Scenario: LLM calls click and Locator.click raises a generic PlaywrightError — ActEvent outcome=error

- **GIVEN** a click whose target raises a generic Playwright error (e.g. `"element not interactable"`)
- **WHEN** the loop dispatches click and `Locator.click(timeout=5000)` raises `playwright.sync_api.Error`
- **THEN** an `ActEvent` SHALL be emitted with `outcome="error"`
- **AND** the tool result SHALL be an error string starting with `"Error: click error"`
- **AND** the loop SHALL continue (SHALL NOT terminate the run)

#### Scenario: LLM calls done with valid evidence — loop exits succeeded

- **GIVEN** the LLM emits a `done` tool call with a non-empty `result` and `evidence` dict containing `url` (non-empty string) and `text_snippet` (non-empty string)
- **WHEN** the loop processes the tool call
- **THEN** the loop SHALL return `RunResult(status="succeeded", result=<result>, evidence=<evidence>, verifier={"ok": True, "reasons": []})`
- **AND** SHALL NOT make any further LLM calls

#### Scenario: LLM calls fail — loop exits failed

- **GIVEN** the LLM emits a `fail` tool call with a `reason` string
- **WHEN** the loop processes the tool call
- **THEN** the loop SHALL return `RunResult(status="failed", result=None, evidence=None, verifier=None)`
- **AND** SHALL NOT make any further LLM calls

## ADDED Requirements

### Requirement: click tool dispatch in loop

The loop SHALL handle `tool_call.name == "click"` in `_dispatch`. The dispatch contract is:

1. Call `_locate_with_supervisor(page, intent, supervisor, cache=locator_cache, trace_writer=trace_writer, run_id=run_id, step_id=step_id)` to resolve the element.
2. Record `url_before = page.url`.
3. Call `page.locator(result.selector).click(timeout=5000)`.
4. If click succeeds: compare `page.url` to `url_before`. If changed → `outcome="nav"`, else → `outcome="ok"`.
5. If `playwright.sync_api.TimeoutError` raised → `outcome="timeout"`.
6. If any other `playwright.sync_api.Error` raised → `outcome="error"`.
7. Emit `ActEvent(tool="click", args={"intent": intent}, outcome=<outcome>, diff={}, ms=<elapsed_ms>)`.
8. Return a string summarising the outcome to the LLM (e.g. `"Clicked 'Submit button' (ok)"` or `"Error: click timeout for intent 'Submit button'"`).
9. On `LocatorMiss` from `_locate_with_supervisor` (all tiers exhausted): return an error string and continue (do NOT terminate the run).

The `ToolName` literal in `loop.py` SHALL be updated to include `"click"`.

#### Scenario: click dispatch returns ok string when element found and clicked

- **GIVEN** a page with a `<button>Submit</button>` element that L1 locates successfully
- **WHEN** `_dispatch("click", {"intent": "Submit button"}, browser, supervisor, ...)` is called
- **THEN** it SHALL return a non-error string (not starting with `"Error:"`)
- **AND** an `ActEvent` with `outcome="ok"` SHALL be emitted

#### Scenario: click dispatch returns error string on LocatorMiss — loop continues

- **GIVEN** a page with no button element (all tiers miss)
- **WHEN** `_dispatch("click", {"intent": "Nonexistent button"}, browser, supervisor, ...)` is called
- **THEN** it SHALL return a string starting with `"Error:"`
- **AND** the loop SHALL NOT terminate; it SHALL append the error string as a tool result and continue to the next iteration
