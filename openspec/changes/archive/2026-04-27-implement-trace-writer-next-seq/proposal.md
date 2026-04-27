## Why

`loop.py` carries a local `plan_seq` counter that it passes as `seq` when constructing `PlanEvent` objects for the `TraceWriter`. This works only because `loop()` is currently the sole writer of events for a given run. As soon as any second emitter (e.g. `ObservationEvent` / `DecisionEvent` / `LLMCallEvent` wiring, per ticket #20) appends events to the same `TraceWriter` for the same `run_id`, the local counter and `TraceWriter`'s `MAX(seq)` check will diverge and raise `SeqError`. Centralising the next-seq query inside `TraceWriter` eliminates the counter entirely and makes all emitters coordination-free.

## What Changes

- `TraceWriter` gains a public method `next_seq(run_id: str) -> int` that queries `MAX(seq)` from `traces_events` for the given run and returns `MAX(seq) + 1` (or `1` if no events exist yet). The run must be open; `LookupError` is raised otherwise.
- `_emit_plan_event` in `loop.py` is updated to call `trace_writer.next_seq(run_id)` instead of incrementing `plan_seq`. The `seq` parameter is removed from `_emit_plan_event`'s signature.
- The local `plan_seq: int = 0` counter in `loop()` is removed entirely.
- The in-memory `events: list | None` path is unchanged; it still writes `PlanEvent` with `seq=0` and `run_id="loop"` as before (placeholder values only used in tests).

## Capabilities

### New Capabilities

- `trace-writer-next-seq`: Public `TraceWriter.next_seq(run_id)` method that returns the next strictly-increasing seq for a run, enabling coordination-free multi-emitter writes.

### Modified Capabilities

- `plan-event-trace-writer`: The `_emit_plan_event` helper no longer accepts a `seq` argument and no longer depends on a local counter in `loop()`; it calls `next_seq()` at emit time instead.

## Impact

- `task2/agent/trace.py`: Add `next_seq(run_id: str) -> int` to `TraceWriter`.
- `task2/agent/loop.py`: Remove `plan_seq` counter; remove `seq` parameter from `_emit_plan_event`; update both call-sites.
- `task2/tests/agent/test_trace.py`: New `next_seq` unit tests.
- `task2/tests/agent/test_loop.py`: Existing `TraceWriter` tests remain; new integration test verifying two interleaved emitters produce strictly-increasing seq.
- No changes to `task2/api/server.py`, `task2/api/db.py`, or any schema models.
