## Context

`agent/loop.py` already has a `_stuck_buf` rolling buffer (added by ticket #70 / PR #104) that catches the case where the LLM repeatedly emits the same tool call K=3 times. However this mechanism is blind to a second failure shape: the LLM emits text-only responses with no tool calls at all. In that shape the buffer never receives entries, so the stuck check never fires, and the loop runs to `max_steps` burning full token/cost budget. `webvoyager-1` exhibited this pattern in two consecutive benchmark runs (`task2-implement-loop-stuck-repeat` and `task2-fix-qwen-http-400`), each spending ~$0.30 + 280s with zero useful output.

The existing `RunResultReason = Literal["stuck_repeat"]` and the `RunResult.reason` field (also added by ticket #70) provide exactly the right extension point: we extend the Literal and add a parallel counter path.

## Goals / Non-Goals

**Goals:**
- Add `_consecutive_no_tool_call_steps` counter to `loop()` that fires at K=3 consecutive text-only responses (for `step_num > 0`).
- Return `RunResult(status="failed", reason="no_tool_call_repeat", ...)` with full metric fields on trigger.
- Extend `RunResultReason` to `Literal["stuck_repeat", "no_tool_call_repeat"]`.
- Cover with two focused unit tests (K=3 text-only → fail; tool call between two text-only → reset).

**Non-Goals:**
- Ticket #72 (observation-digest companion heuristic) — separate ticket, not in scope here.
- Changing `_stuck_buf` or `_STUCK_REPEAT_K` behavior.
- Modifying benchmarks or the score script.
- Altering prompts or any other agent module.

## Decisions

### D1 — Counter-based approach (not a ring buffer)

A simple integer counter is sufficient: we only need to know whether the last K responses were all tool-call-free. No per-entry deduplication is needed (unlike `_stuck_buf`, which compares entries for identity). Counter is O(1) in both space and time.

**Alternative considered:** a parallel `list[bool]` ring buffer mirroring `_stuck_buf` structure. Rejected as needlessly complex when a counter carries exactly the same information for this use-case.

### D2 — Gate on `step_num > 0`

Step 0 is the planning step: `plan_module.plan()` is called directly and the LLM response never goes through the `response.tool_calls` path. The counter is only updated inside the `for _ in range(max_steps)` body, after `step_num` has been incremented. The check fires only when `step_num > 0`. This is trivially satisfied by the loop structure — `step_num` is 1 on the first iteration — so the plan step's implicit "no tool calls" is never counted. However, since step 1 _does_ go through the LLM decision path (after the plan is built), if the LLM emits no tool calls on step 1 that IS a legitimate no-tool-call step and SHOULD count. The gate is therefore simply that the counter logic only lives in the main `for` body (never in the `step_num == 1` plan-call block).

**Alternative considered:** gating on `step_num > 1`. Rejected — that would silently permit one free text-only step even when step 1 already stalls, reducing K from 3 to 2 effective detection count without reason.

### D3 — Counter resets on ANY tool call in a step (not just non-error ones)

Even a tool call that returns an error represents real dispatch — the planner is not stuck in text-only mode. Resetting on any tool call is consistent with `_stuck_buf`'s model and avoids edge cases where a click error is not counted as a tool emission.

### D4 — Early-exit placement: after `_record_step`, mirroring `stuck_repeat`

The `no_tool_call_repeat` exit is placed in the `if not response.tool_calls` branch (currently just `_record_step; continue`). After incrementing the counter, if it hits `_NO_TOOL_CALL_K`, call `_record_step` (same call that was already there) and return the `RunResult` instead of `continue`-ing. This keeps the record/return pattern consistent with how `stuck_repeat` exits.

### D5 — `_NO_TOOL_CALL_K = 3`

Matches `_STUCK_REPEAT_K`. Low enough to limit waste (3 steps ≈ $0.05 at current token rates), high enough not to false-positive on a single-step conversational response.

## Risks / Trade-offs

- [False positive on legitimate multi-turn reasoning] → K=3 is deliberately small; if a future task design intentionally generates 3+ consecutive reasoning turns before tool use, this could misfire. Mitigation: K is a named constant; increase it if false positives appear in benchmarks.
- [Counter does not reset on replan] → Replanning emits a `PlanEvent` but the loop body still goes through the normal `response.tool_calls` path after a replan. If a replan also produces no tool calls, it correctly contributes to the counter. This is the desired behavior: a replan that still produces no tools is equally stuck.

## Migration Plan

No migration needed. The new `"no_tool_call_repeat"` literal value is additive to `RunResultReason`. All existing `RunResult` construction sites that do not set `reason` continue to compile without change.

## Open Questions

None. Ticket #73 fully specifies the constant, counter placement, gating rule, and return shape.
