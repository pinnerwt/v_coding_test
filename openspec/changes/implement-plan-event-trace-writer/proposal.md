## Why

`_emit_plan_event` in `loop.py` writes `PlanEvent` objects with placeholder values (`run_id="loop"`, `seq=0`, `ts=""`) into an in-memory `events: list | None` parameter. Real runs that persist traces via `TraceWriter` will never capture plan events with valid metadata, making plan rows in the JSONL trace either absent or unfaithful compared to the surrounding `ObservationEvent`/`DecisionEvent`/`LLMCallEvent` rows.

## What Changes

- `_emit_plan_event` in `loop.py` gains a `Literal["initial", "replan"]` type annotation on `reason`, removing the existing `# type: ignore[arg-type]` comment.
- The `loop()` function is wired to accept an optional `TraceWriter` parameter alongside the existing `events: list | None` parameter; when a `TraceWriter` is supplied, `PlanEvent` rows are written through it with the run's actual `run_id`, monotonic `seq` (assigned by the writer via its strictly-increasing counter), and ISO-format `ts`.
- The in-memory `events: list | None` path is preserved unchanged (back-compat) — plan events still accumulate there when no `TraceWriter` is provided.
- No double-emit: a single call to `_emit_plan_event` either appends to the in-memory list or writes to the `TraceWriter`, not both.
- The "initial" plan event is written before the first `DecisionEvent`; the "replan" event is written at the supervisor-halt boundary, before the next `DecisionEvent`.

## Capabilities

### New Capabilities

- `plan-event-trace-writer`: Wiring `loop.py` to emit `PlanEvent` rows through `TraceWriter` with real `run_id`, monotonic `seq`, and ISO `ts`, alongside a type-narrowing fix for `_emit_plan_event`'s `reason` parameter.

### Modified Capabilities

- `plan-replan`: The `plan-replan` spec gains a requirement that the in-memory `events: list` path still captures `PlanEvent` objects (back-compat); no schema-level requirements change in `plan-replan` itself.

## Impact

- `task2/agent/loop.py`: `_emit_plan_event`, `loop()` signature, and the two call-sites for `_emit_plan_event`.
- `task2/tests/agent/test_loop.py`: existing tests remain; new tests added for the `TraceWriter` path.
- No changes to `task2/agent/trace.py` (the `PlanEvent` schema and `TraceWriter` are already correct).
- No changes to `task2/agent/plan.py`.
- Callers: `eval/runner.py` and `api/server.py` may pass a `TraceWriter` to `loop()`; they are the only two real callers besides the in-memory test path.
