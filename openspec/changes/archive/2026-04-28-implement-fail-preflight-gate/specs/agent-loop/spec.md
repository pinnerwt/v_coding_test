## MODIFIED Requirements

### Requirement: LLM tool surface exposed by the loop

The loop SHALL expose the following tools to the LLM via `tools` in every `llm_client.chat()` call:

- `goto(url: str)` — navigate the browser to the given URL.
- `read(intent?: str)` — read visible text from the page. If `intent` is provided, the loop SHALL attempt to resolve it via `locate_l1(page, ...)` first. If `locate_l1` raises `LocatorMiss(reason="zero_matches")`, the loop SHALL invoke the `Supervisor` to get an escalation decision. If the supervisor prescribes a next tier (e.g. `"L2_dom"`), the loop SHALL retry resolution at that tier (e.g. via `locate_l2`). If resolution ultimately succeeds, the loop SHALL read the element's text via `Browser.read(selector)` and return it as the tool result. If resolution fails at all tiers, or if the intent text cannot be parsed (`IntentParseError`), the loop SHALL return an error string as the tool result and continue (SHALL NOT terminate the run). If `intent` is absent or empty, the loop SHALL return the full page body text (up to 2000 characters of `document.body.innerText`).
- `click(intent: str)` — click a page element described by `intent`. The loop SHALL resolve the element via `_locate_with_supervisor` (same ladder and cache path used by `read`). On successful resolution the loop SHALL call `Locator.click(timeout=…)` on the resolved Playwright Locator. After the click the loop SHALL emit an `ActEvent` with `outcome` in `{ok, no_effect, nav, timeout, error}`. On `LocatorMiss` from `_locate_with_supervisor` (all tiers exhausted), the loop SHALL return an error string and continue (SHALL NOT terminate the run).
- `type(intent: str, text: str)` — fill a textbox described by `intent` with `text`. The loop SHALL resolve the element via `_locate_with_supervisor` (same ladder and cache path used by `read` and `click`). On successful resolution the loop SHALL call `Locator.fill(text, timeout=5000)` on the resolved Playwright Locator. After the fill the loop SHALL emit an `ActEvent` with `outcome` in `{ok, timeout, error}`. On `LocatorMiss` from `_locate_with_supervisor` (all tiers exhausted), the loop SHALL return an error string and continue (SHALL NOT terminate the run).
- `done(result: object, evidence: {url: str, text_snippet: str})` — terminal tool: mark the task complete. The loop SHALL validate the evidence and exit with either `RunResult(status="succeeded", ...)` or `RunResult(status="unverified", ...)` depending on the validation result.
- `fail(reason: str)` — terminal tool: mark the task failed. Under normal conditions the loop SHALL exit with `RunResult(status="failed", result=None, evidence=None, verifier=None)`. The loop SHALL apply the pre-flight validation gate (see Requirement: fail pre-flight validation gate) before accepting a `fail` call as terminal.

The loop SHALL NOT expose `select`, `wait_for`, `back`, or `screenshot`; those are added when tests demand them.

#### Scenario: LLM calls fail with no prior interaction on step 1 — call rejected, loop continues

- **GIVEN** a stub LLM that emits `fail(reason="I cannot find anything")` on step 1
- **AND** no `click` or `type` with a successful outcome has been dispatched before this step
- **WHEN** the loop encounters the `fail` tool call
- **THEN** the loop SHALL NOT return `RunResult(status="failed")`
- **AND** a `SupervisorEvent(classified_as="premature_fail")` SHALL be emitted
- **AND** the tool result appended to the message thread SHALL contain the remaining step budget and the substring `"click"` or `"type"`
- **AND** the loop SHALL continue to the next iteration

#### Scenario: LLM calls fail after a successful click — fail is honored normally

- **GIVEN** a stub LLM that emits `click(intent="Submit button")` on step 1 (outcome ok) and then `fail(reason="page did not load")` on step 2
- **WHEN** the loop encounters the `fail` tool call on step 2
- **THEN** the loop SHALL return `RunResult(status="failed", result=None, evidence=None, verifier=None)` immediately
- **AND** no `SupervisorEvent(classified_as="premature_fail")` SHALL be emitted

#### Scenario: LLM calls fail with an irrecoverable reason on step 1 — fail is honored immediately

- **GIVEN** a stub LLM that emits `fail(reason="login wall detected")` on step 1
- **AND** no prior `click` or `type` has occurred
- **WHEN** the loop encounters the `fail` tool call
- **THEN** the loop SHALL return `RunResult(status="failed", result=None, evidence=None, verifier=None)` immediately
- **AND** no `SupervisorEvent(classified_as="premature_fail")` SHALL be emitted

## ADDED Requirements

### Requirement: fail pre-flight validation gate

Before the loop accepts a `fail` tool call as terminal, it SHALL apply a pre-flight check. The check fires when BOTH of the following conditions hold:

- `step_num <= 1` — the `fail` call arrives on the first step of the run.
- No prior actionable outcome has been recorded for `click` or `type` in this run — i.e., no `click` dispatch returned `outcome` in `{"ok", "nav"}` and no `type` dispatch returned `outcome="ok"`.

When both conditions hold AND the `reason` string does NOT contain any irrecoverable keyword (case-insensitive substring match against `_IRRECOVERABLE_REASONS = frozenset({"login wall", "captcha", "blocked"})`), the loop SHALL:

1. Emit a `SupervisorEvent(classified_as="premature_fail", policy="halt", attempt=1)` via `_emit_supervisor_event` (or append to `events` when `trace_writer` is `None`).
2. Append a nudge string as the tool result: `"you have {max_steps - step_num} steps left and have not attempted to interact — try \`click\`/\`type\` first."` where `{max_steps - step_num}` is the number of steps remaining at the time of rejection.
3. Continue the loop to the next iteration (SHALL NOT return `RunResult(status="failed")`).

In all other cases — `step_num > 1`, or a prior actionable outcome exists, or the `reason` contains an irrecoverable keyword — the loop SHALL accept the `fail` call and return `RunResult(status="failed", result=None, evidence=None, verifier=None)` as before.

The loop SHALL track prior actionable outcomes in a local list `_prior_act_outcomes: list[str]` that is initialized to `[]` at the start of `loop()` and appended to whenever a `click` dispatch produces `outcome in {"ok", "nav"}` or a `type` dispatch produces `outcome == "ok"`. This list SHALL NOT persist across `loop()` invocations.

#### Scenario: step-1 fail with no prior interaction emits premature_fail SupervisorEvent

- **GIVEN** `loop()` is called with `max_steps=10`
- **AND** a stub LLM that emits `fail(reason="nothing useful here")` on step 1
- **AND** no `click` or `type` was dispatched before this step
- **WHEN** the `fail` branch is reached
- **THEN** a `SupervisorEvent` with `classified_as="premature_fail"` SHALL be emitted (or appended to `events` when `trace_writer` is `None`)
- **AND** the tool result SHALL contain `"9 steps left"` (i.e., `max_steps - step_num = 10 - 1 = 9`)
- **AND** the tool result SHALL contain `"click"` and `"type"`
- **AND** the loop SHALL NOT return at this point; it SHALL continue to the next step

#### Scenario: fail on step 2 after step-1 read is honored normally

- **GIVEN** a stub LLM that emits `read()` on step 1 and `fail(reason="could not find result")` on step 2
- **AND** no `click` or `type` was dispatched
- **WHEN** the `fail` branch is reached on step 2
- **THEN** the loop SHALL return `RunResult(status="failed")` immediately
- **AND** no `SupervisorEvent(classified_as="premature_fail")` SHALL be emitted

#### Scenario: fail with reason containing "login wall" is honored on step 1

- **GIVEN** a stub LLM that emits `fail(reason="Encountered a login wall")` on step 1
- **AND** no prior `click` or `type` occurred
- **WHEN** the `fail` branch is reached
- **THEN** the loop SHALL return `RunResult(status="failed")` immediately (irrecoverable keyword match)
- **AND** no `SupervisorEvent(classified_as="premature_fail")` SHALL be emitted

#### Scenario: fail with reason containing "captcha" is honored on step 1

- **GIVEN** a stub LLM that emits `fail(reason="CAPTCHA encountered, cannot proceed")` on step 1
- **AND** no prior `click` or `type` occurred
- **WHEN** the `fail` branch is reached
- **THEN** the loop SHALL return `RunResult(status="failed")` immediately
- **AND** no `SupervisorEvent(classified_as="premature_fail")` SHALL be emitted

#### Scenario: step-1 fail after successful click is honored normally

- **GIVEN** a stub LLM that emits `click(intent="Submit button")` on step 1 (outcome ok) then `fail(reason="submit failed")` on step 1 (second tool call in same step)
- **WHEN** the `fail` branch is reached
- **THEN** `_prior_act_outcomes` is non-empty (contains `"ok"` from the click)
- **AND** the loop SHALL return `RunResult(status="failed")` immediately
- **AND** no `SupervisorEvent(classified_as="premature_fail")` SHALL be emitted
