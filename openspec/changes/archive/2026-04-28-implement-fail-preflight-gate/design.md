## Context

`agent/loop.py` dispatches the `fail` tool call unconditionally: when `tool_call.name == "fail"` is detected in the main `for` loop, it immediately calls `_record_step` and returns `RunResult(status="failed", ...)`. There is no check on step number or prior event history.

`agent/trace.py` defines `SupervisorEvent.classified_as` as a closed `Literal["LocatorMiss","Ambiguous","NoEffect","FormError","NavDrift","Blocked","Timeout"]`. The new class `"premature_fail"` does not exist yet.

The `events: list | None` parameter is already threaded into `loop()` and populated with `_DecisionMarker` instances during each step. However, `ActEvent` objects are emitted to `trace_writer`, not to `events`. The guardrail needs to inspect prior actions. The cleanest signal is `_emit_act_event` calls already in `_dispatch` for `click` and `type` — but those write to `trace_writer`, not to `events`. To avoid coupling the guardrail to `trace_writer`, the `fail` branch will track prior actionable outcomes via a local list `_prior_act_outcomes: list[str]` that is updated whenever `click` or `type` dispatches successfully (outcome in `{ok, nav}`). This list is accumulated within `loop()` and inspected in the `fail` branch.

Five benchmark cases follow the `read → fail` shape where the model reads the page once, finds no clear next action, and gives up at step 1. The guardrail cuts this mode by one free rejection before the model is forced to try `click` or `type`.

## Goals / Non-Goals

**Goals:**
- Reject `fail` on `step_num <= 1` when no `click`/`type` with a successful outcome has been recorded in `_prior_act_outcomes`.
- Emit `SupervisorEvent(classified_as="premature_fail")` for every rejection.
- Append a nudge string as the tool result so the model sees its remaining budget and is prompted to try interaction.
- Honor `fail` unconditionally when `reason` contains an irrecoverable keyword (`"login wall"`, `"captcha"`, `"blocked"`).
- Honor `fail` unconditionally when `step_num > 1` OR when `_prior_act_outcomes` is non-empty.
- Add `"premature_fail"` to `SupervisorEvent.classified_as` Literal in `agent/trace.py`.

**Non-Goals:**
- Changing `agent/supervisor.py`, `agent/browser.py`, `agent/locate.py`, or fixture HTML.
- Tracking `_prior_act_outcomes` beyond the scope of a single `loop()` invocation.
- Guarding against premature `done` calls (separate concern).
- Expanding the irrecoverable keyword list beyond the three listed above.

## Decisions

**Decision: use a local `_prior_act_outcomes: list[str]` in `loop()` rather than inspecting `trace_writer`.**

The `trace_writer` may be `None` (most unit tests omit it). Inspecting it would introduce an optional-reader code path. A simple list accumulator — updated in the `click` and `type` dispatch branches when `outcome in _CLICK_SUCCESS_OUTCOMES` or `outcome == "ok"` — is already adjacent to the relevant dispatch code and adds zero coupling.

**Decision: the irrecoverable keyword check is a `str.lower()` substring match against `args.get("reason", "")`.**

The ticket names `"login wall"` and `"captcha"` as examples. A case-insensitive substring match is minimal and avoids regex complexity. The keyword list is a module-level frozen set: `_IRRECOVERABLE_REASONS: frozenset[str] = frozenset({"login wall", "captcha", "blocked"})`.

**Decision: `step_num <= 1` as the threshold, not `step_num == 1`.**

The ticket says "step ≤ 1 of a budget-N run." In the current loop, `step_num` starts at 1 and increments before the `fail` branch is reached. A step-1 `fail` arrives when `step_num == 1`. The condition `step_num <= 1` is equivalent but written to match ticket wording exactly.

**Decision: `SupervisorEvent.trigger_event_seq` is unconditionally set to `0` for `premature_fail` events.**

`trigger_event_seq` is always `0`, regardless of whether `trace_writer` and `run_id` are provided. The spec permits this (see `specs/trace-schema-writer/spec.md:7`, "MAY be set to `0`"). The rationale: a premature_fail by definition fires when `_prior_act_outcomes` is empty — there has been no prior Locate or Act event in this iteration that could serve as the triggering event, so `0` is the canonical "no trigger" sentinel rather than a synthetic `next_seq - 1` value.

**Decision: nudge string format is `f"you have {max_steps - step_num} steps left and have not attempted to interact — try \`click\`/\`type\` first."`**

This matches the ticket verbatim. `max_steps - step_num` gives remaining steps at the time of rejection (the current step is not counted as consumed since it did not terminate the loop).

**Decision: the actionable-outcome predicate is inlined as `not _prior_act_outcomes` — no standalone helper.**

The simplify pass collapsed the originally-planned private helper into a direct truthiness check on `_prior_act_outcomes`. Since the list only ever receives values from successful click/type dispatches (outcome in `{"ok", "nav"}` for click, `"ok"` for type), an empty list is equivalent to "no actionable outcome recorded." The inline `not _prior_act_outcomes` check is simpler and avoids an unnecessary module-level function.

## Risks / Trade-offs

- **Risk: the guardrail fires on a legitimate step-1 `fail` where the model correctly detected an unrecoverable state but used a non-keyword reason string.** → Mitigation: the irrecoverable keyword list covers the three canonical cases from the benchmark. A one-step nudge costs at most one extra LLM call; if the model re-calls `fail` on step 2, it is honored.
- **Risk: `_prior_act_outcomes` accumulates across ALL tool calls in the step, not just successful ones.** → Mitigation: only outcomes in `{"ok", "nav"}` (for `click`) or `{"ok"}` (for `type`) append to the list. Error outcomes do not count as actionable.
- **Risk: `SupervisorEvent` Pydantic validation fails if `classified_as` is not updated before the emitter code lands.** → Mitigation: `trace.py` change (step 2.1) is listed before the `loop.py` change (step 2.2) in tasks.md; the red test for the new literal is in step 1.1.

## Open Questions

*(none — all design decisions follow directly from the ticket text and the existing codebase patterns)*
