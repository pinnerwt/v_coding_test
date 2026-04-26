## MODIFIED Requirements

### Requirement: LLM tool surface exposed by the loop

The loop SHALL expose the following tools to the LLM via `tools` in every `llm_client.chat()` call:

- `goto(url: str)` — navigate the browser to the given URL.
- `read(intent?: str)` — read visible text from the page. If `intent` is provided, the loop SHALL attempt to resolve it via `locate_l1(page, ...)` first. If `locate_l1` raises `LocatorMiss(reason="zero_matches")`, the loop SHALL invoke the `Supervisor` to get an escalation decision. If the supervisor prescribes a next tier (e.g. `"L2_dom"`), the loop SHALL retry resolution at that tier (e.g. via `locate_l2`). If resolution ultimately succeeds, the loop SHALL read the element's text via `Browser.read(selector)` and return it as the tool result. If resolution fails at all tiers, the loop SHALL return an error string as the tool result and continue. If `intent` is absent or empty, the loop SHALL return the full page body text (up to 2000 characters of `document.body.innerText`).
- `done(result: object, evidence: {url: str, text_snippet: str})` — terminal tool: mark the task complete. The loop SHALL validate the evidence and exit with either `RunResult(status="succeeded", ...)` or `RunResult(status="unverified", ...)` depending on the validation result.
- `fail(reason: str)` — terminal tool: mark the task failed. The loop SHALL exit with `RunResult(status="failed", result=None, evidence=None, verifier=None)`.

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

### Requirement: loop observation uses AX-tree digest

The loop SHALL call `observe.build_observation(browser, last_action)` at the start of each step instead of constructing the observation inline. The returned dict (with keys `url`, `title`, `ax_tree_digest`, `ax_fingerprint`, `last_action`) SHALL be serialized to JSON and appended to the LLM message thread as a user message prefixed by `STATE_MESSAGE_PREFIX`. The loop SHALL track `last_action` across steps: on the first step it SHALL be `None`; after each tool dispatch it SHALL be updated to `{tool: <name>, intent: <string summary of args>, outcome: <"ok"|"error">, error?: <message>}`.

#### Scenario: First step has last_action null in observation

- **GIVEN** a fresh loop invocation (step 1)
- **WHEN** the loop calls `observe.build_observation(browser, last_action)` for the first time
- **THEN** `last_action` SHALL be `None`
- **AND** the serialized user message SHALL contain `"last_action": null`

#### Scenario: Second step threads previous last_action

- **GIVEN** a loop where step 1 dispatched a `goto` tool call that succeeded
- **WHEN** the loop calls `observe.build_observation(browser, last_action)` at the start of step 2
- **THEN** `last_action` SHALL be a dict with at least keys `tool` (value `"goto"`) and `outcome` (value `"ok"`)
- **AND** the serialized user message SHALL contain the `last_action` dict

#### Scenario: Observation message contains ax_tree_digest key

- **GIVEN** a loop step where `observe.build_observation` returns a dict with `ax_tree_digest`
- **WHEN** the loop appends the observation to the LLM message thread
- **THEN** the serialized JSON SHALL contain the key `"ax_tree_digest"`
- **AND** SHALL NOT contain the legacy key `"text"` (the old innerText observation)
