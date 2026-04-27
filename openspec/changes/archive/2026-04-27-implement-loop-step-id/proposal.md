## Why

`_emit_plan_event` and `_emit_locate_event` in `agent/loop.py` both hardcode `step_id=None` when constructing `PlanEvent` and `LocateEvent` instances, even though `EventBase.step_id: str | None` exists precisely for per-step attribution. Without a populated `step_id`, plan and locate trace rows cannot be joined back to the loop step that produced them, making per-step diagnostics (e.g. "which step did a cache invalidation fire on?", "which step triggered replan?") impossible from the trace alone — the `_aggregate_diagnostics` path in `scripts/eval.py` must guess by position instead.

## What Changes

- Define a `step_id` format convention: `f"{run_id}:step-{step_num}"` where `step_num` is the loop's existing `step_num` counter (1-indexed, already incremented at the top of every loop iteration).
- Add a `step_id: str | None` parameter to `_emit_plan_event` and `_emit_locate_event`; both helpers forward it into the event constructor instead of hardcoding `None`.
- Thread `step_id` from `loop()` into each `_emit_plan_event` call-site (initial plan at step 1, replan at the supervisor-halt boundary) passing the current `step_num`.
- Thread `step_id` from `loop()` into `_dispatch`, then from `_dispatch` into `_locate_with_supervisor`, then from `_locate_with_supervisor` into `_emit_locate_event` for each cache action (read-hit, invalidate, write).
- The in-memory `events` list path (used by test fixtures) receives the same `step_id` — no separate handling.

## Capabilities

### New Capabilities

- `loop-step-id`: `PlanEvent` and `LocateEvent` rows written through `TraceWriter` (or the in-memory `events` list) carry a non-`None` `step_id` formatted as `"{run_id}:step-{step_num}"` that identifies the loop iteration that produced the event.

### Modified Capabilities

- `agent-loop`: `_dispatch` and `_locate_with_supervisor` gain a `step_id: str | None` parameter; `loop()` constructs the step identifier and threads it through on every step iteration.
- `plan-event-trace-writer`: `_emit_plan_event` gains a `step_id` parameter; the emitted `PlanEvent` rows have non-`None` `step_id` when called from `loop()` with a `run_id`.

## Impact

- `task2/agent/loop.py` — signature changes for `_emit_plan_event`, `_emit_locate_event`, `_dispatch`, `_locate_with_supervisor`, and the two `_emit_plan_event` call-sites and all `_emit_locate_event` call-sites inside `_locate_with_supervisor`.
- `task2/tests/agent/test_loop.py` — new tests asserting `step_id` correctness on `PlanEvent` and `LocateEvent` rows; existing in-memory `events` tests must continue passing.
- No changes to `task2/agent/trace.py` — `EventBase.step_id` already exists.
- No changes to `task2/scripts/eval.py` or `task2/api/server.py` (callers pass `run_id` which is sufficient for the loop to construct the `step_id` internally).
- No schema migrations, no new dependencies, no Zeabur impact.
