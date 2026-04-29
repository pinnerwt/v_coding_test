## ADDED Requirements

### Requirement: RunResult carries an optional reason field

`agent.loop.RunResult` SHALL gain an additional field `reason: RunResultReason | None = None`, where `RunResultReason = Literal["stuck_repeat"]` is a module-level alias declared alongside `RunStatus`. The field SHALL default to `None` so all existing construction sites that do not pass `reason` continue to compile and run without modification. When the loop exits via stuck-state early-termination, the field SHALL be set to `"stuck_repeat"`. For all other terminal paths (`done`, `fail`, `timeout`, supervisor halt) the field SHALL remain `None` unless explicitly set by that path. Future failure modes SHALL be added as deliberate extensions of the `RunResultReason` Literal alias rather than as free-text strings.

#### Scenario: RunResult constructed without reason defaults to None

- **WHEN** `RunResult(status="succeeded", result={}, evidence={"url": "http://x", "text_snippet": "x"})` is constructed
- **THEN** `result.reason` SHALL be `None`

#### Scenario: RunResult constructed with reason preserves the value

- **WHEN** `RunResult(status="failed", result=None, evidence=None, reason="stuck_repeat")` is constructed
- **THEN** `result.reason` SHALL equal `"stuck_repeat"`

### Requirement: Loop terminates early when LLM emits K identical tool calls in a row

`agent.loop.loop()` SHALL maintain a rolling buffer `_stuck_buf` of the last `_STUCK_REPEAT_K` canonical tool-call strings, where each entry is `f"{tool_name}:{json.dumps(args, sort_keys=True)}"` and `_STUCK_REPEAT_K = 3` is a module-level constant. After each LLM response that contains at least one tool call, the loop SHALL dispatch each tool call, append the canonical string for that call to `_stuck_buf`, trim `_stuck_buf` to the last `_STUCK_REPEAT_K` entries, and check whether all `_STUCK_REPEAT_K` entries are byte-identical. If they are, the loop SHALL immediately call `_record_step(...)` and return:

- `RunResult(status="failed", reason="stuck_repeat", result=None, evidence=None, verifier=None, steps=step_num, ...)`

The `_stuck_buf` SHALL be initialized to `[]` at the start of `loop()` and SHALL NOT be reset between steps (it is a rolling window across the entire run). However, if the supervisor handles a tool call during dispatch (detected by snapshotting the supervisor's attempt count before dispatch and observing an increase after), the buffer SHALL be cleared, and the current call's canonical entry SHALL then be appended to the empty buffer. This ensures supervisor-mediated repetition is owned by the supervisor's halt/replan path rather than stuck-detection.

#### Scenario: Three identical goto calls in a row trigger stuck exit at step 3

- **GIVEN** a stub `LLMClient` that always returns `goto(url="about:blank")` as its tool call (no `done`/`fail`)
- **AND** `loop()` is called with `max_steps=20`
- **WHEN** the loop runs
- **THEN** `RunResult.status` SHALL equal `"failed"`
- **AND** `RunResult.reason` SHALL equal `"stuck_repeat"`
- **AND** `RunResult.steps` SHALL equal `3` (exits at step 3, not step 20)

#### Scenario: Healthy alternation of tool calls runs to natural completion without false-positive stuck detection

- **GIVEN** a stub `LLMClient` that emits `goto(url="http://a")` on step 1, `goto(url="http://b")` on step 2, `goto(url="http://a")` on step 3, and a no-tool-call response on step 4 (alternating URLs prevent all K entries from being identical)
- **AND** `loop()` is called with `max_steps=20`
- **WHEN** the loop runs
- **THEN** `RunResult.status` SHALL equal `"timeout"`
- **AND** `RunResult.reason` SHALL be `None`

#### Scenario: Stuck exit fires before max_steps is exhausted for non-supervisor tools

- **GIVEN** a stub `LLMClient` that always returns the same `goto(url="about:blank")` tool call
- **AND** `loop()` is called with `max_steps=20`
- **WHEN** the loop runs
- **THEN** `RunResult.steps` SHALL be less than `20`
- **AND** `RunResult.status` SHALL equal `"failed"`
- **AND** `RunResult.reason` SHALL equal `"stuck_repeat"`
