## MODIFIED Requirements

### Requirement: RunResult carries an optional reason field

`agent.loop.RunResult` SHALL carry a field `reason: RunResultReason | None = None`, where `RunResultReason = Literal["stuck_repeat", "no_tool_call_repeat"]` is a module-level alias declared alongside `RunStatus`. The field SHALL default to `None` so all existing construction sites that do not pass `reason` continue to compile and run without modification. When the loop exits via stuck-state early-termination (K identical tool calls), the field SHALL be set to `"stuck_repeat"`. When the loop exits via no-tool-call early-termination (K consecutive responses with no tool calls), the field SHALL be set to `"no_tool_call_repeat"`. For all other terminal paths (`done`, `fail`, `timeout`, supervisor halt) the field SHALL remain `None` unless explicitly set by that path. Future failure modes SHALL be added as deliberate extensions of the `RunResultReason` Literal alias rather than as free-text strings.

#### Scenario: RunResult constructed without reason defaults to None

- **WHEN** `RunResult(status="succeeded", result={}, evidence={"url": "http://x", "text_snippet": "x"})` is constructed
- **THEN** `result.reason` SHALL be `None`

#### Scenario: RunResult constructed with stuck_repeat reason preserves the value

- **WHEN** `RunResult(status="failed", result=None, evidence=None, reason="stuck_repeat")` is constructed
- **THEN** `result.reason` SHALL equal `"stuck_repeat"`

#### Scenario: RunResult constructed with no_tool_call_repeat reason preserves the value

- **WHEN** `RunResult(status="failed", result=None, evidence=None, reason="no_tool_call_repeat")` is constructed
- **THEN** `result.reason` SHALL equal `"no_tool_call_repeat"`

## ADDED Requirements

### Requirement: Loop terminates early when LLM emits K consecutive responses with no tool calls

`agent.loop.loop()` SHALL maintain a counter `_consecutive_no_tool_call_steps` initialized to `0` at the start of `loop()`, alongside a module-level constant `_NO_TOOL_CALL_K = 3`. On each step where `step_num > 0` and the LLM response yields `len(response.tool_calls) == 0` (or `None`), the counter SHALL be incremented by 1. On each step where the LLM response yields at least one tool call, the counter SHALL be reset to `0`. When the counter reaches `_NO_TOOL_CALL_K`, the loop SHALL immediately call `_record_step(...)` and return:

- `RunResult(status="failed", reason="no_tool_call_repeat", result=None, evidence=None, verifier=None, steps=step_num, prompt_tokens=cum_prompt_tokens, completion_tokens=cum_completion_tokens, usd=cum_usd, latency_ms_total=sum(latency_ms_per_step), latency_ms_per_step=latency_ms_per_step, step_breakdown=step_breakdown)`

The plan step at step 0 (where `plan_module.plan()` is called directly and the LLM response does not pass through the tool-call dispatch path) SHALL NOT count toward the `_consecutive_no_tool_call_steps` counter. This is naturally satisfied by the counter only being updated inside the `for _ in range(max_steps)` body after `step_num` is incremented to at least `1`.

#### Scenario: Three consecutive no-tool-call responses trigger no_tool_call_repeat exit at step 3

- **GIVEN** a stub `LLMClient` that always returns `ChatResponse(content="...", tool_calls=[])` for every non-plan call (no `done`/`fail`/navigation tool)
- **AND** `loop()` is called with `max_steps=20`
- **WHEN** the loop runs
- **THEN** `RunResult.status` SHALL equal `"failed"`
- **AND** `RunResult.reason` SHALL equal `"no_tool_call_repeat"`
- **AND** `RunResult.steps` SHALL equal `3` (exits at step 3, not step 20)

#### Scenario: A tool call between two no-tool-call steps resets the counter and loop runs to timeout

- **GIVEN** a stub `LLMClient` that returns no-tool-call responses on steps 1 and 2, then returns `goto(url="http://example.com")` on step 3, then returns no-tool-call responses for all remaining steps
- **AND** `loop()` is called with `max_steps=20`
- **WHEN** the loop runs
- **THEN** the counter resets to `0` on step 3 (the `goto` step)
- **AND** `RunResult.status` SHALL equal `"timeout"` (runs to `max_steps` after counter reset rather than failing at step 2)
- **AND** `RunResult.steps` SHALL equal `20`

#### Scenario: No-tool-call exit fires before max_steps is exhausted

- **GIVEN** a stub `LLMClient` that always returns text-only responses with no tool calls
- **AND** `loop()` is called with `max_steps=20`
- **WHEN** the loop runs
- **THEN** `RunResult.steps` SHALL be less than `20`
- **AND** `RunResult.status` SHALL equal `"failed"`
- **AND** `RunResult.reason` SHALL equal `"no_tool_call_repeat"`
