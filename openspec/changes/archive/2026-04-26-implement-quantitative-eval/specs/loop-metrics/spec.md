## ADDED Requirements

### Requirement: RunResult carries quantitative metrics

`agent.loop.RunResult` SHALL gain the following additional fields (all with defaults so existing callers need not change):

- `steps: int = 0` — number of observe→decide→act iterations completed.
- `prompt_tokens: int = 0` — total prompt tokens across all LLM calls in the run.
- `completion_tokens: int = 0` — total completion tokens across all LLM calls.
- `usd: float = 0.0` — total USD cost across all LLM calls.
- `latency_ms_total: int = 0` — total wall time in milliseconds across all steps.
- `latency_ms_per_step: list[int] = field(default_factory=list)` — wall time in ms for each step, index 0 = step 1.
- `step_breakdown: list[dict] = field(default_factory=list)` — one dict per step with keys: `step` (int, 1-based), `latency_ms` (int), `prompt_tokens` (int), `completion_tokens` (int), `usd` (float), `tool_calls` (list[str]).

All new fields SHALL be populated by `loop()` after a real run with at least one step.

#### Scenario: RunResult is still constructible without new fields

- **WHEN** code constructs `RunResult(status="succeeded", result={}, evidence={"url": "x", "text_snippet": "y"})` without specifying metric fields
- **THEN** the construction SHALL succeed
- **AND** `steps` SHALL equal `0`, `prompt_tokens` SHALL equal `0`, `usd` SHALL equal `0.0`

#### Scenario: Frozen constraint still holds

- **WHEN** code attempts to assign `run_result.steps = 5` after construction
- **THEN** it SHALL raise `dataclasses.FrozenInstanceError`

### Requirement: loop() populates RunResult metrics

`loop()` SHALL populate all metric fields in the returned `RunResult`. Specifically:

- `steps` SHALL equal the number of completed observe→decide→act iterations (not counting the final terminal call as an additional step unless it consumed an LLM call).
- `prompt_tokens` SHALL equal the sum of `response.usage.prompt_tokens` for every `llm_client.chat()` call.
- `completion_tokens` SHALL equal the sum of `response.usage.completion_tokens` for every call.
- `usd` SHALL equal the sum of `response.usd` for every call (where `response.usd` is computed by `LLMClient` via the price table).
- `latency_ms_per_step` SHALL have exactly `steps` elements.
- `latency_ms_total` SHALL equal `sum(latency_ms_per_step)`.
- `step_breakdown` SHALL have exactly `steps` elements, each a dict with the required keys.

#### Scenario: Synthetic 2-step run produces non-zero metrics

- **GIVEN** a mocked `LLMClient` that returns on step 1 a `goto` tool call with `usage(prompt=100, completion=10)` and `usd=0.00022`, and on step 2 a `done` call with `usage(prompt=150, completion=20)` and `usd=0.00034`
- **AND** a stub `Browser` that does not raise
- **WHEN** `loop("task", browser, llm_client, max_steps=5)` is called
- **THEN** `result.steps` SHALL equal `2`
- **AND** `result.prompt_tokens` SHALL equal `250`
- **AND** `result.completion_tokens` SHALL equal `30`
- **AND** `result.usd` SHALL be approximately `0.00056`
- **AND** `result.latency_ms_total` SHALL be greater than `0`
- **AND** `len(result.latency_ms_per_step)` SHALL equal `2`
- **AND** `len(result.step_breakdown)` SHALL equal `2`

#### Scenario: Each step_breakdown entry has required keys

- **GIVEN** a loop run that completes at least one step
- **WHEN** `result.step_breakdown[0]` is inspected
- **THEN** it SHALL have keys `step`, `latency_ms`, `prompt_tokens`, `completion_tokens`, `usd`, `tool_calls`
- **AND** `step_breakdown[0]["step"]` SHALL equal `1`

#### Scenario: timeout path still populates partial metrics

- **GIVEN** a mocked LLM that never calls `done` or `fail` within `max_steps`
- **WHEN** `loop("task", browser, llm_client, max_steps=2)` returns
- **THEN** `result.status` SHALL equal `"timeout"`
- **AND** `result.steps` SHALL equal `2`
- **AND** `result.latency_ms_per_step` SHALL have `2` elements
