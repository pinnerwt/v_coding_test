## Why

Benchmark analysis on 2026-04-28 identified 5 runs sharing the same failure shape: the model emits `fail` on step 1 or step 2 before making any `click` or `type` attempt. With `click` (#59) and `type` (#60) now in the tool surface, and the system prompt tightened (#61), the residual cause is the model voluntarily bailing before it ever touches the page. A structural guardrail is the missing piece: when the model calls `fail` on step ≤ 1 with no prior actionable interaction in the event log, the loop should reject the call, emit a `SupervisorEvent(classified_as="premature_fail")`, and inject a one-line nudge into the next prompt instead of terminating the run early.

## What Changes

- Add `"premature_fail"` to the `classified_as: Literal[...]` of `SupervisorEvent` in `agent/trace.py`. This is a net-new classification value — the existing values (`"LocatorMiss"`, `"Ambiguous"`, `"NoEffect"`, `"FormError"`, `"NavDrift"`, `"Blocked"`, `"Timeout"`) are unchanged.
- Add a pre-flight check in the `fail` branch of the main loop (in `agent/loop.py`): before accepting a `fail` call, check whether `step_num <= 1` and no prior event in the run's event list represents an actionable outcome (`click` or `type` ActEvent with `outcome` in `{ok, nav}`). If both conditions are true, reject the call: emit `SupervisorEvent(classified_as="premature_fail")`, append a tool-result nudge string to the message thread, and continue the loop iteration without returning.
- The nudge string injected as the tool result is: `"you have {max_steps - step_num} steps left and have not attempted to interact — try \`click\`/\`type\` first."` (where `max_steps - step_num` is the remaining step budget at the time of rejection).
- Irrecoverable conditions recognized by keyword in `reason` (e.g. `"login wall"`, `"captcha"`, `"blocked"`) bypass the guardrail and are honored on any step — `fail` is accepted immediately.
- A `fail` call on step > 1 with at least one prior `click`/`type` attempt is always honored normally (no guardrail fires).
- No changes to `agent/supervisor.py`, `agent/browser.py`, `agent/locate.py`, or any test fixture HTML.

## Capabilities

### New Capabilities

*(none — this is a loop-level guardrail extension, not a new standalone capability)*

### Modified Capabilities

- `agent-loop`: the `LLM tool surface exposed by the loop` requirement currently states that `fail(reason: str)` is a terminal tool that unconditionally exits with `RunResult(status="failed", ...)`. It must be updated to document the pre-flight condition under which `fail` is rejected and the loop continues.
- `trace-schema-writer`: the `SupervisorEvent model` requirement currently lists `classified_as` as a closed `Literal` without `"premature_fail"`. It must be updated to add `"premature_fail"` to that literal.

## Impact

- `task2/agent/trace.py` — `SupervisorEvent.classified_as` Literal gains `"premature_fail"`.
- `task2/agent/loop.py` — `fail` branch in the main `for` loop gains a pre-flight check using `_has_actionable_outcome` (new private helper) and emits `SupervisorEvent(classified_as="premature_fail")` before continuing.
- `task2/tests/` — three new test functions covering: (a) step-1 `fail` with no prior interaction is rejected, (b) `fail` after step 1 with a prior `click` is honored, (c) `fail` with an irrecoverable reason keyword is honored on any step.
