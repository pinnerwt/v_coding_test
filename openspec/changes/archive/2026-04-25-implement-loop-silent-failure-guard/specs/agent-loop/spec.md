## MODIFIED Requirements

### Requirement: RunResult dataclass

The system SHALL provide `agent.loop.RunResult` — a frozen dataclass representing the outcome of a completed loop run. It SHALL have the following fields:

- `status: str` — one of `"succeeded"`, `"unverified"`, `"failed"`, `"timeout"`.
- `result: object | None` — structured result data if the task completed successfully; `None` otherwise.
- `evidence: dict | None` — evidence dict provided to `done()`; `None` when the loop did not complete via `done`.
- `verifier: dict | None` — for `done` exits: `{"ok": bool, "reasons": list[str]}` recording the evidence check outcome. `None` for `fail` and `timeout` exits.

`RunResult` SHALL be frozen so callers cannot mutate it after construction.

#### Scenario: RunResult is constructible and frozen

- **WHEN** code constructs `RunResult(status="succeeded", result={"heading": "Hello"}, evidence={"url": "http://...", "text_snippet": "Hello"})`
- **THEN** the construction SHALL succeed
- **AND** attempting to assign to any field SHALL raise `dataclasses.FrozenInstanceError`

#### Scenario: RunResult status values are distinguishable

- **WHEN** the loop exits via `done()` with valid evidence (url + text_snippet both non-empty strings)
- **THEN** `RunResult.status` SHALL equal `"succeeded"`
- **WHEN** the loop exits via `done()` with missing or invalid evidence
- **THEN** `RunResult.status` SHALL equal `"unverified"`
- **WHEN** the loop exits via `fail(reason)`
- **THEN** `RunResult.status` SHALL equal `"failed"`
- **WHEN** the step count reaches `max_steps` without a terminal tool call
- **THEN** `RunResult.status` SHALL equal `"timeout"`

### Requirement: LLM tool surface exposed by the loop

The loop SHALL expose the following tools to the LLM via `tools` in every `llm_client.chat()` call:

- `goto(url: str)` — navigate the browser to the given URL.
- `read(intent?: str)` — read visible text from the page. If `intent` is provided, the loop SHALL attempt to resolve it via `locate_l1(page, ...)` first. If `locate_l1` raises `LocatorMiss(reason="zero_matches")`, the loop SHALL invoke the `Supervisor` to get an escalation decision. If the supervisor prescribes a next tier (e.g. `"L2_dom"`), the loop SHALL retry resolution at that tier (e.g. via `locate_l2`). If resolution ultimately succeeds, the loop SHALL read the element's text via `Browser.read(selector)` and return it as the tool result. If resolution fails at all tiers, the loop SHALL return an error string as the tool result and continue. If `intent` is absent or empty, the loop SHALL return the full page body text (up to 2000 characters of `document.body.innerText`).
- `done(result: object, evidence: {url: str, text_snippet: str})` — terminal tool: mark the task complete. The loop SHALL validate the evidence and exit with either `RunResult(status="succeeded", ...)` or `RunResult(status="unverified", ...)` depending on the validation result (see Requirement: done evidence guard below).
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

### Requirement: done evidence guard

When the LLM calls the `done` tool, the loop SHALL validate the `evidence` argument before committing to `status="succeeded"`. The guard checks two required fields:

- `url`: must be present in the evidence dict and be a non-empty string (after stripping whitespace).
- `text_snippet`: must be present in the evidence dict and be a non-empty string (after stripping whitespace).

If either field is absent, not a string, or empty after stripping whitespace, the guard SHALL mark the run `"unverified"`. The guard SHALL construct a `verifier` dict of shape `{"ok": bool, "reasons": list[str]}` that records which checks failed. This `verifier` dict SHALL be attached to the `RunResult`.

`screenshot_ref` is part of the planned `DoneEvent.evidence` shape but is NOT validated by this guard; its validation is deferred to the screenshot-diff feature (a separate future ticket).

#### Scenario: done called with empty evidence dict — status is unverified

- **GIVEN** the LLM emits a `done` tool call with `evidence={}`
- **WHEN** the loop processes the tool call
- **THEN** `RunResult.status` SHALL equal `"unverified"`
- **AND** `RunResult.verifier["ok"]` SHALL be `False`
- **AND** `RunResult.verifier["reasons"]` SHALL be a non-empty list of strings describing the missing fields

#### Scenario: done called with evidence missing text_snippet — status is unverified

- **GIVEN** the LLM emits a `done` tool call with `evidence={"url": "http://example.com"}`
- **WHEN** the loop processes the tool call
- **THEN** `RunResult.status` SHALL equal `"unverified"`
- **AND** `RunResult.verifier["ok"]` SHALL be `False`
- **AND** `RunResult.verifier["reasons"]` SHALL mention `text_snippet`

#### Scenario: done called with evidence missing url — status is unverified

- **GIVEN** the LLM emits a `done` tool call with `evidence={"text_snippet": "some text"}`
- **WHEN** the loop processes the tool call
- **THEN** `RunResult.status` SHALL equal `"unverified"`
- **AND** `RunResult.verifier["ok"]` SHALL be `False`
- **AND** `RunResult.verifier["reasons"]` SHALL mention `url`

#### Scenario: done called with no evidence argument — status is unverified

- **GIVEN** the LLM emits a `done` tool call with no `evidence` key in args
- **WHEN** the loop processes the tool call
- **THEN** `RunResult.status` SHALL equal `"unverified"`
- **AND** `RunResult.verifier["ok"]` SHALL be `False`

#### Scenario: done called with valid evidence — status is succeeded, verifier ok

- **GIVEN** the LLM emits a `done` tool call with `evidence={"url": "http://example.com", "text_snippet": "Hello"}`
- **WHEN** the loop processes the tool call
- **THEN** `RunResult.status` SHALL equal `"succeeded"`
- **AND** `RunResult.verifier["ok"]` SHALL be `True`
- **AND** `RunResult.verifier["reasons"]` SHALL be an empty list

#### Scenario: existing happy-path test stays green

- **GIVEN** a mock LLM that emits `done` with `evidence={"url": <fixture_url>, "text_snippet": "Hello, loop"}`
- **WHEN** `loop(task, browser, mock_llm_client)` is called
- **THEN** `RunResult.status` SHALL equal `"succeeded"` (no regression from ticket #9)
- **AND** `RunResult.evidence["url"]` and `RunResult.evidence["text_snippet"]` SHALL be non-empty strings
