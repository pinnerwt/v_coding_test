# agent-loop Specification

## Purpose
TBD - created by archiving change implement-loop-happy-path. Update Purpose after archive.
## Requirements
### Requirement: RunResult dataclass

The system SHALL provide `agent.loop.RunResult` — a frozen dataclass representing the outcome of a completed loop run. It SHALL have the following fields:

- `status: str` — one of `"succeeded"`, `"failed"`, `"timeout"`.
- `result: object | None` — structured result data if the task completed successfully; `None` otherwise.
- `evidence: dict | None` — evidence dict provided to `done()`; `None` when the loop did not complete successfully.

`RunResult` SHALL be frozen so callers cannot mutate it after construction.

#### Scenario: RunResult is constructible and frozen

- **WHEN** code constructs `RunResult(status="succeeded", result={"heading": "Hello"}, evidence={"url": "http://...", "text_snippet": "Hello"})`
- **THEN** the construction SHALL succeed
- **AND** attempting to assign to any field SHALL raise `dataclasses.FrozenInstanceError`

#### Scenario: RunResult status values are distinguishable

- **WHEN** the loop exits via `done()` with valid evidence
- **THEN** `RunResult.status` SHALL equal `"succeeded"`
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
- `read(intent?: str)` — read visible text from the page. If `intent` is provided, the loop SHALL resolve it via `locate(page, intent)` to find the target element and return its text. If `intent` is absent or empty, the loop SHALL return the full page body text (up to 2000 characters of `document.body.innerText`).
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
- **THEN** the loop SHALL call `locate(page, "the article heading")` to resolve the element
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

