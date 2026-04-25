## MODIFIED Requirements

### Requirement: LLM tool surface exposed by the loop

The loop SHALL expose the following tools to the LLM via `tools` in every `llm_client.chat()` call:

- `goto(url: str)` — navigate the browser to the given URL.
- `read(intent?: str)` — read visible text from the page. If `intent` is provided, the loop SHALL attempt to resolve it via `locate_l1(page, ...)` first. If `locate_l1` raises `LocatorMiss(reason="zero_matches")`, the loop SHALL invoke the `Supervisor` to get an escalation decision. If the supervisor prescribes a next tier (e.g. `"L2_dom"`), the loop SHALL retry resolution at that tier (e.g. via `locate_l2`). If resolution ultimately succeeds, the loop SHALL read the element's text via `Browser.read(selector)` and return it as the tool result. If resolution fails at all tiers, the loop SHALL return an error string as the tool result and continue. If `intent` is absent or empty, the loop SHALL return the full page body text (up to 2000 characters of `document.body.innerText`).
- `done(result: object, evidence: {url: str, text_snippet: str})` — terminal tool: mark the task succeeded. The loop SHALL exit with `RunResult(status="succeeded", result=result, evidence=evidence)`.
- `fail(reason: str)` — terminal tool: mark the task failed. The loop SHALL exit with `RunResult(status="failed", result=None, evidence=None)`.

The loop SHALL NOT expose `click`, `type`, `select`, `wait_for`, `back`, or `screenshot` in this ticket; those are added when tests demand them.

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

#### Scenario: LLM calls done — loop exits succeeded

- **GIVEN** the LLM emits a `done` tool call with a non-empty `result` and `evidence` dict containing `url` and `text_snippet`
- **WHEN** the loop processes the tool call
- **THEN** the loop SHALL return `RunResult(status="succeeded", result=<result>, evidence=<evidence>)`
- **AND** SHALL NOT make any further LLM calls

#### Scenario: LLM calls fail — loop exits failed

- **GIVEN** the LLM emits a `fail` tool call with a `reason` string
- **WHEN** the loop processes the tool call
- **THEN** the loop SHALL return `RunResult(status="failed", result=None, evidence=None)`
- **AND** SHALL NOT make any further LLM calls

## ADDED Requirements

### Requirement: Loop self-correction via supervisor escalation

When the `read` tool dispatch encounters a `LocatorMiss(reason="zero_matches")` from the initial locate attempt, the loop SHALL invoke the `Supervisor` to classify the miss and obtain an escalation decision. If the supervisor returns `next_tier="L2_dom"`, the loop SHALL retry locate at L2. If L2 succeeds, the loop SHALL use the L2 result to read the element and return the text. If the supervisor halts (no `next_tier`), the loop SHALL return an error string as the tool result and continue. This requirement is the acceptance criterion for ticket #10.

The `Supervisor` instance SHALL be created once per `loop()` invocation so that attempt counters accumulate correctly across multiple locate failures within the same run.

#### Scenario: L1 fails with zero_matches, L2 succeeds — loop self-corrects

- **GIVEN** a fixture page where a button has `aria-label="action"` (so `get_by_role("button", name="Submit")` returns zero matches) but has visible text "Submit" (so `locate_l2` with role="button", name="Submit" succeeds)
- **AND** a mock LLM that emits: step 1 → `goto(url=<fixture_url>)`, step 2 → `read(intent="Submit button")`, step 3 → `done(result={"clicked": true}, evidence={...})`
- **WHEN** `loop(task, browser, mock_llm_client)` is called
- **THEN** the loop SHALL attempt L1 locate for "Submit button", receive `LocatorMiss(reason="zero_matches")`
- **AND** invoke the `Supervisor` which SHALL return `next_tier="L2_dom"`
- **AND** retry via L2 which SHALL succeed
- **AND** return `RunResult(status="succeeded")` after the `done` call

#### Scenario: Supervisor escalation path is exercised — test fails without wiring

- **GIVEN** `loop.py` does NOT wire the supervisor into read dispatch (supervisor is never called)
- **WHEN** the self-correction test fixture is used and `read(intent="Submit button")` is dispatched
- **THEN** the loop SHALL either raise an unhandled `LocatorMiss` or return an error tool result that prevents the LLM from calling `done`
- **AND** the test SHALL fail, confirming the test is a valid regression guard

#### Scenario: Supervisor max_attempts cap — loop halts gracefully after exhaustion

- **GIVEN** the supervisor's `max_attempts` is reached for the `(current_tier, reason)` pair
- **WHEN** the loop calls `supervisor.handle(miss, current_tier=...)`
- **THEN** the supervisor SHALL return `EscalationDecision(next_tier=None, policy="halt", ...)`
- **AND** the loop SHALL feed an error string back to the LLM as the tool result (not raise or crash)
- **AND** continue to the next loop iteration
