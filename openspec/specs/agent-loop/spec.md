# agent-loop Specification

## Purpose
TBD - created by archiving change implement-loop-happy-path. Update Purpose after archive.
## Requirements
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

### Requirement: loop function

The system SHALL provide `agent.loop.loop(task, browser, llm_client, *, max_steps=20)` — a synchronous function that drives the observe → decide → act cycle. Parameters:

- `task: str` — natural-language task description, verbatim as given by the caller.
- `browser: agent.browser.Browser` — an already-open `Browser` instance (inside a `with` block; the loop does not open or close it).
- `llm_client: agent.llm.LLMClient` — an already-constructed `LLMClient`; the loop calls `llm_client.chat(messages, tools=TOOLS)`.
- `max_steps: int = 20` — maximum number of observe→decide→act iterations before returning `status="timeout"`.

The function SHALL return a `RunResult`.

#### Scenario: loop returns RunResult

- **WHEN** `loop(task, browser, llm_client)` is called with a valid `Browser` and `LLMClient`
- **THEN** it SHALL return a `RunResult` instance

#### Scenario: loop is bounded by max_steps

- **WHEN** the LLM never calls `done` or `fail` within `max_steps` iterations
- **THEN** the loop SHALL return `RunResult(status="timeout", result=None, evidence=None)`

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

### Requirement: Happy-path 2-step task completion

The system SHALL support completing a 2-step task on a local HTML fixture: step 1 navigate to a page, step 2 read a value and call `done` with valid evidence. This is the acceptance criterion for ticket #9.

The evidence dict passed to `done` SHALL contain at minimum `url` (the current page URL) and `text_snippet` (a non-empty string of visible page text confirming the result). The loop SHALL treat any non-empty evidence dict with these two keys as valid for the happy path.

#### Scenario: 2-step task completes with succeeded status

- **GIVEN** a local HTML fixture page with a known heading
- **AND** a mock LLM that emits: step 1 → `goto(url=<fixture_url>)`, step 2 → `done(result={"heading": <text>}, evidence={"url": <fixture_url>, "text_snippet": <text>})`
- **WHEN** `loop(task, browser, mock_llm_client)` is called
- **THEN** the return value SHALL be a `RunResult` with `status="succeeded"`
- **AND** `RunResult.evidence` SHALL be a dict with non-empty `url` and `text_snippet` values
- **AND** `RunResult.result` SHALL be the dict passed to `done`

#### Scenario: Evidence is present in the RunResult

- **GIVEN** a successful `done` call with `evidence={"url": "http://127.0.0.1:<port>/loop_happy_path.html", "text_snippet": "Hello, loop"}`
- **WHEN** the loop returns
- **THEN** `RunResult.evidence["url"]` SHALL be a non-empty string
- **AND** `RunResult.evidence["text_snippet"]` SHALL be a non-empty string

### Requirement: LLM_BASE_URL and LLM_MODEL remain configurable

The loop SHALL NOT hardcode any LLM provider URL or model name. All LLM configuration SHALL come from the `LLMClient` instance passed to `loop()`. The loop SHALL pass `llm_client` through unmodified; it SHALL NOT construct its own `LLMClient` internally.

#### Scenario: Loop uses caller-supplied LLMClient

- **WHEN** `loop(task, browser, llm_client)` is called with a custom `LLMClient` configured to use a specific `base_url`
- **THEN** all LLM calls in the loop SHALL go through that `llm_client` instance
- **AND** the loop SHALL NOT read `LLM_BASE_URL` or `LLM_MODEL` environment variables directly

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

