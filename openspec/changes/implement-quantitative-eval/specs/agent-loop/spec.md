## MODIFIED Requirements

### Requirement: RunResult dataclass

The system SHALL provide `agent.loop.RunResult` — a frozen dataclass representing the outcome of a completed loop run. It SHALL have the following fields:

- `status: str` — one of `"succeeded"`, `"unverified"`, `"failed"`, `"timeout"`.
- `result: object | None` — structured result data if the task completed successfully; `None` otherwise.
- `evidence: dict | None` — evidence dict provided to `done()`; `None` when the loop did not complete via `done`.
- `verifier: dict | None` — for `done` exits: `{"ok": bool, "reasons": list[str]}` recording the evidence check outcome. `None` for `fail` and `timeout` exits.
- `steps: int = 0` — number of completed observe→decide→act iterations.
- `prompt_tokens: int = 0` — cumulative prompt tokens across all LLM calls.
- `completion_tokens: int = 0` — cumulative completion tokens across all LLM calls.
- `usd: float = 0.0` — cumulative USD cost across all LLM calls.
- `latency_ms_total: int = 0` — total wall time in ms across all steps.
- `latency_ms_per_step: list[int]` — per-step wall time in ms (length equals `steps`).
- `step_breakdown: list[dict]` — per-step breakdown dicts (length equals `steps`).

`RunResult` SHALL be frozen so callers cannot mutate it after construction.

#### Scenario: RunResult is constructible and frozen

- **WHEN** code constructs `RunResult(status="succeeded", result={"heading": "Hello"}, evidence={"url": "http://...", "text_snippet": "Hello"})`
- **THEN** the construction SHALL succeed
- **AND** `steps` SHALL equal `0` (default)
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

The system SHALL provide `agent.loop.loop(task, browser, llm_client, *, max_steps=20)` — a synchronous function that drives the observe → decide → act cycle and returns a `RunResult` with all metric fields populated.

- `steps` SHALL equal the number of completed observe→decide→act iterations.
- `prompt_tokens`, `completion_tokens`, `usd` SHALL be cumulated from each `llm_client.chat()` response.
- `latency_ms_per_step` SHALL have one entry per step (wall time for the full observe→decide→dispatch cycle).
- `latency_ms_total` SHALL equal `sum(latency_ms_per_step)`.
- `step_breakdown[i]` SHALL have `step=i+1`, `latency_ms`, `prompt_tokens`, `completion_tokens`, `usd`, `tool_calls` (list of tool name strings called in that step).

#### Scenario: loop returns RunResult

- **WHEN** `loop(task, browser, llm_client)` is called with a valid `Browser` and `LLMClient`
- **THEN** it SHALL return a `RunResult` instance

#### Scenario: loop is bounded by max_steps

- **WHEN** the LLM never calls `done` or `fail` within `max_steps` iterations
- **THEN** the loop SHALL return `RunResult(status="timeout", result=None, evidence=None)` with `steps == max_steps`

#### Scenario: Metrics are non-zero after a successful 2-step run

- **GIVEN** a mocked `LLMClient` that returns a `goto` tool call on step 1 (usage: 100 prompt, 10 completion, usd 0.00022) and `done` on step 2 (usage: 150 prompt, 20 completion, usd 0.00034)
- **WHEN** the loop completes
- **THEN** `result.steps` SHALL equal `2`
- **AND** `result.prompt_tokens` SHALL equal `250`
- **AND** `result.completion_tokens` SHALL equal `30`
- **AND** `result.usd` SHALL be approximately `0.00056`
- **AND** `result.latency_ms_total` SHALL be positive
