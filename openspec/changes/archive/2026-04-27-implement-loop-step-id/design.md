## Context

`EventBase.step_id: str | None` has existed in `agent/trace.py` since the trace schema was written, but `loop.py` never populates it: both `_emit_plan_event` and `_emit_locate_event` hardcode `step_id=None`. The loop already maintains a `step_num: int` counter (incremented at the top of every loop iteration starting at 1) and a `run_id: str | None` kwarg. The missing piece is simply wiring `f"{run_id}:step-{step_num}"` into the two emit helpers and threading it down the call chain.

The call chain from `loop()` to event emission is:

```
loop()
  └── _emit_plan_event(...)            # called at step 1 (initial) and at halt (replan)
  └── _dispatch(...)
        └── _locate_with_supervisor(...)
              └── _emit_locate_event(...)  # called on cache hit / invalidate / write
```

No other helpers emit `PlanEvent` or `LocateEvent`. The fix is purely additive: add one parameter to each link in the chain.

Ticket #20 (`ObservationEvent` / `DecisionEvent` wiring) is the consistency anchor — whatever format that ticket adopts for `step_id` must match ours. The ticket text suggests `f"{run_id}:step-{i}"`. We adopt that exact format so the two changes are compatible.

## Goals / Non-Goals

**Goals:**
- `PlanEvent` and `LocateEvent` rows produced by a `loop()` run carry `step_id = f"{run_id}:step-{step_num}"` when `run_id` is not `None`.
- The in-memory `events: list` path (used by existing tests) also receives the populated `step_id` — no special-casing.
- The format `"{run_id}:step-{step_num}"` is documented as the canonical format so ticket #20 can match it.
- All existing tests pass without modification.

**Non-Goals:**
- Wiring `step_id` into `ObservationEvent`, `DecisionEvent`, `LLMCallEvent`, `ActEvent`, or `SupervisorEvent` — that is ticket #20.
- Changing `TraceWriter` or the trace schema — `EventBase.step_id` already exists.
- Changing `scripts/eval.py` or `api/server.py` — callers already pass `run_id`; the loop derives `step_id` internally.
- Supporting a caller-configurable `step_id` format — one format, defined here.

## Decisions

### Decision: Format `"{run_id}:step-{step_num}"` — colon separator, 1-indexed

The ticket text proposes `f"{run_id}:step-{i}"`. We use `step_num` (the loop's existing counter, 1-indexed) as `i`. The colon separator ensures the two components are visually distinct and avoids ambiguity with hyphens that appear in ULIDs. `step_num` is 1-indexed because that is how the loop already uses it (`step_num += 1` at the top of the loop body before any emission).

Alternative considered: 0-indexed `step-0`, `step-1`, etc. Rejected because `step_num` is already 1-indexed everywhere else in the loop (e.g. `step_breakdown` entries have `"step": step_num`); using a different base would create an off-by-one confusion between `step_breakdown` and trace rows.

Alternative considered: `f"step-{step_num}"` without `run_id` prefix. Rejected because `step_id` is stored in `traces_events` alongside `run_id`; adding the prefix makes a `step_id` value self-describing and joinable without requiring the outer `run_id` column.

### Decision: `step_id` is `None` when `run_id` is `None`

When `loop()` is called without a `run_id` (e.g. the in-memory events path with `run_id=None`), `step_id` is `None`. This preserves backward compatibility: callers that do not pass `run_id` see no change in event shape.

Alternative considered: invent a synthetic run_id when none is provided. Rejected because it would break the semantic that `step_id` can always be decomposed back to a real `run_id` + step index, and the in-memory path is only used in tests where `step_id=None` is acceptable.

### Decision: Pass `step_id` as a parameter, not re-derive it inside helpers

`_emit_plan_event` and `_emit_locate_event` receive `step_id: str | None` as an argument rather than `(run_id, step_num)` to reconstruct it themselves. This keeps the format construction in one place (inside `loop()`), avoids duplicating the format string, and makes the helpers simpler.

Alternative considered: pass `(run_id, step_num)` to helpers and construct the string there. Rejected because it couples helpers to the format convention and doubles the number of parameters.

### Decision: Thread `step_id` through `_dispatch` and `_locate_with_supervisor`

`_dispatch` already accepts `trace_writer` and `run_id` for the `_locate_with_supervisor` call. Adding `step_id: str | None = None` follows the same pattern and requires no structural changes. `_locate_with_supervisor` similarly gains `step_id: str | None = None` and passes it to `_emit_locate_event`.

Alternative considered: store `step_id` on the `Supervisor` instance so helpers can read it without parameter threading. Rejected because `Supervisor` is a domain object (failure classification) and should not carry tracing state; the parameter threading is straightforward and explicit.

## Risks / Trade-offs

- **Risk**: Ticket #20 adopts a different `step_id` format, making plan/locate rows inconsistent with observation/decision rows.
  → Mitigation: the chosen format `"{run_id}:step-{step_num}"` is explicitly documented here. Ticket #20 should reference this decision. If ticket #20 diverges, a follow-up refactor normalises both.

- **Risk**: A future caller constructs `step_id` differently outside `loop()`.
  → Mitigation: format construction is in one place (inside `loop()`); external callers that emit `PlanEvent` or `LocateEvent` directly would need to follow the same convention.

## Migration Plan

No schema or API migration. The change is additive (new parameter with default `None`). All existing callers of `_dispatch`, `_locate_with_supervisor`, `_emit_plan_event`, and `_emit_locate_event` that do not pass `step_id` continue to work with `step_id=None` in the emitted event — same as today.

Deployment: standard `uv sync` + Zeabur redeploy. Rollback: revert the two file changes.

## Open Questions

None — the format is defined, the call chain is clear, and the scope is bounded to `loop.py`.
