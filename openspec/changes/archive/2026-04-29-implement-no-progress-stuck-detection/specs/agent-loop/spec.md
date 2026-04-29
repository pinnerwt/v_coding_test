## MODIFIED Requirements

### Requirement: RunResult carries an optional reason field

`agent.loop.RunResult` SHALL carry a field `reason: RunResultReason | None = None`, where `RunResultReason = Literal["stuck_repeat", "no_tool_call_repeat", "seconds_budget", "no_progress"]` is a module-level alias declared alongside `RunStatus`. The field SHALL default to `None` so all existing construction sites that do not pass `reason` continue to compile and run without modification. When the loop exits via stuck-state early-termination (K identical tool calls), the field SHALL be set to `"stuck_repeat"`. When the loop exits via no-tool-call early-termination (K consecutive responses with no tool calls), the field SHALL be set to `"no_tool_call_repeat"`. When the loop exits via wall-clock budget exhaustion, the field SHALL be set to `"seconds_budget"`. When the loop exits via no-progress stuck detection (N consecutive steps with same AX fingerprint and no successful action), the field SHALL be set to `"no_progress"`. For all other terminal paths (`done`, `fail`, `timeout` from `max_steps`, supervisor halt) the field SHALL remain `None` unless explicitly set by that path. Future failure modes SHALL be added as deliberate extensions of the `RunResultReason` Literal alias rather than as free-text strings.

#### Scenario: RunResult constructed without reason defaults to None

- **WHEN** `RunResult(status="succeeded", result={}, evidence={"url": "http://x", "text_snippet": "x"})` is constructed
- **THEN** `result.reason` SHALL be `None`

#### Scenario: RunResult constructed with stuck_repeat reason preserves the value

- **WHEN** `RunResult(status="failed", result=None, evidence=None, reason="stuck_repeat")` is constructed
- **THEN** `result.reason` SHALL equal `"stuck_repeat"`

#### Scenario: RunResult constructed with no_tool_call_repeat reason preserves the value

- **WHEN** `RunResult(status="failed", result=None, evidence=None, reason="no_tool_call_repeat")` is constructed
- **THEN** `result.reason` SHALL equal `"no_tool_call_repeat"`

#### Scenario: RunResult constructed with no_progress reason preserves the value

- **WHEN** `RunResult(status="failed", result=None, evidence=None, reason="no_progress")` is constructed
- **THEN** `result.reason` SHALL equal `"no_progress"`

## ADDED Requirements

### Requirement: Loop terminates early when N consecutive steps share an unchanged AX fingerprint and emit no successful action

`agent.loop.loop()` SHALL maintain a parallel rolling buffer `_no_progress_buf` of the last `_NO_PROGRESS_K` per-step tuples, alongside a module-level constant `_NO_PROGRESS_K = 4`. This buffer is entirely separate from the existing `_stuck_buf` (which tracks per-tool-call byte-identical repetition); both mechanisms run concurrently and whichever fires first wins.

At the end of each step's tool-call dispatch loop (after all tool calls in the LLM response have been dispatched and before `_record_step` is called for the normal step completion path), the loop SHALL:

- Capture the post-dispatch AX fingerprint by calling `observe.build_observation(browser, []).get("ax_fingerprint")`.
- Determine `any_action_succeeded: bool` — `True` iff at least one `click`, `type`, `goto`, or `read` tool call dispatched in this step returned a result string that does **not** start with `"Error:"`. `goto` and `read` are included alongside `click`/`type` because they represent observable progress: `goto` mutates URL/page state, and `read` retrieves information the LLM uses to make subsequent decisions. Excluding them produces false positives when the agent legitimately navigates and then explores via reads (the live smoke pattern: `goto example.com` step 1 → `read` body steps 2-N → `done` — fingerprint stays constant from step 1 onward).
- Append `(post_ax_fingerprint, any_action_succeeded)` to `_no_progress_buf`.
- Trim `_no_progress_buf` to the last `_NO_PROGRESS_K` entries (remove from the front if over length).
- Check: if `len(_no_progress_buf) == _NO_PROGRESS_K` AND all entries share the same fingerprint AND all entries have `any_action_succeeded == False`, then call `_record_step(...)` and return `RunResult(status="failed", reason="no_progress", result=None, evidence=None, verifier=None, steps=step_num, prompt_tokens=cum_prompt_tokens, completion_tokens=cum_completion_tokens, usd=cum_usd, latency_ms_total=sum(latency_ms_per_step), latency_ms_per_step=latency_ms_per_step, step_breakdown=step_breakdown)`.

`_no_progress_buf` SHALL be initialized to `[]` at the start of `loop()` and SHALL NOT be reset between steps. It SHALL NOT be reset on L1→L2 supervisor escalations (unlike `_stuck_buf`) — supervisor-mediated outcomes are already reflected in `any_action_succeeded`. It SHALL be cleared when a `replan` is triggered (i.e. when the supervisor policy is `"halt"` and `replan_used` is `False`), because `replan` constitutes a strategy reset that invalidates the prior observation window; this is distinct from a simple L1→L2 escalation.

The `_no_progress_buf` check SHALL run only on steps where the tool-call loop completed without an earlier `_stuck_buf` bail. It SHALL NOT run on steps with no tool calls (those are handled by `_consecutive_no_tool_call_steps`).

The `latency_breakdown_ms` dict MUST be present on the bailing step's record (the existing `_record_step` call handles this via `_phase_breakdown`).

#### Scenario: Constant fingerprint with no successful click, type, goto, or read exits at step 4 with reason no_progress

- **GIVEN** a stub `LLMClient` that emits `read({"intent": f"x{i}"})` on each step (different args each step, so `_stuck_buf` never fills)
- **AND** a stub `Browser` whose `build_observation()` always returns the same `ax_fingerprint` (constant hash)
- **AND** the `read` tool dispatch returns an error string each step (locator missed, intent unmatched)
- **AND** `loop()` is called with `max_steps=20`
- **WHEN** the loop runs
- **THEN** `RunResult.status` SHALL equal `"failed"`
- **AND** `RunResult.reason` SHALL equal `"no_progress"`
- **AND** `RunResult.steps` SHALL equal `4` (bails at step 4, not step 20)

#### Scenario: Alternating fingerprint prevents no_progress detection and loop runs to max_steps

- **GIVEN** a stub `LLMClient` that emits `read({"intent": f"x{i}"})` on each step
- **AND** a stub `Browser` whose `build_observation()` alternates between two distinct `ax_fingerprint` values on successive calls (e.g. `"aaaa"` on even steps, `"bbbb"` on odd steps)
- **AND** `loop()` is called with `max_steps=6`
- **WHEN** the loop runs
- **THEN** `RunResult.status` SHALL NOT equal `"failed"` with `reason="no_progress"` (the buffer never fills with a uniform fingerprint)
- **AND** the loop SHALL run until another termination condition fires (e.g. `max_steps` or `no_tool_call_repeat`)

#### Scenario: Constant fingerprint but click returned ok does not trigger no_progress bail

- **GIVEN** a stub `LLMClient` that emits a `click({"intent": "button"})` tool call on every step
- **AND** a stub `Browser` whose `build_observation()` always returns the same `ax_fingerprint`
- **AND** the `click` dispatch always returns `"Clicked 'button' (ok)"` (outcome `ok`, non-error string)
- **AND** `loop()` is called with `max_steps=20`
- **WHEN** the loop runs
- **THEN** `RunResult.reason` SHALL NOT equal `"no_progress"` (each step has `any_action_succeeded=True`, so the buffer never satisfies the bail condition)

#### Scenario: no_progress exit emits a complete step record with latency_breakdown_ms

- **GIVEN** a stub setup that triggers the no_progress exit condition at step 4
- **WHEN** `RunResult` is returned with `reason="no_progress"`
- **THEN** `RunResult.step_breakdown` SHALL have exactly `4` entries
- **AND** every entry in `step_breakdown` SHALL have a `latency_breakdown_ms` key with integer fields `observation_ms`, `llm_ms`, and `dispatch_ms`

#### Scenario: replan clears the no_progress buffer so post-replan steps start a fresh window

- **GIVEN** a run that has accumulated some entries in `_no_progress_buf` (but fewer than `_NO_PROGRESS_K`)
- **AND** the supervisor triggers a `replan` (policy `"halt"`, `replan_used == False`)
- **WHEN** the replan completes and execution continues
- **THEN** `_no_progress_buf` SHALL be empty and the no_progress bail counter starts fresh from zero

#### Scenario: existing stuck_repeat test is unaffected by no_progress buffer

- **GIVEN** a stub `LLMClient` that always returns `goto(url="about:blank")` (same tool call with identical args each step)
- **AND** `loop()` is called with `max_steps=20`
- **WHEN** the loop runs
- **THEN** `RunResult.reason` SHALL equal `"stuck_repeat"` (fires at step 3 via `_stuck_buf`, before `_no_progress_buf` can accumulate 4 entries)
- **AND** `RunResult.steps` SHALL equal `3`
