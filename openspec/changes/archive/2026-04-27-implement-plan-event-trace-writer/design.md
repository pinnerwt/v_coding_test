## Context

`loop.py` uses `_emit_plan_event` to create `PlanEvent` objects. Currently this function only writes into an in-memory `events: list | None` parameter with placeholder metadata (`run_id="loop"`, `seq=0`, `ts=""`). Real production runs (via `api/server.py`) create a `TraceWriter` but do not pass it to `loop()`, so plan events never appear in the persisted JSONL trace. The existing in-memory path is used solely by tests.

`TraceWriter` already manages strictly-increasing `seq` assignment and ISO timestamp generation for `ObservationEvent`, `DecisionEvent`, and other event kinds. `PlanEvent` belongs in the same stream but is currently excluded.

## Goals / Non-Goals

**Goals:**
- Wire `loop()` to accept an optional `TraceWriter` so `PlanEvent` rows are persisted with the run's actual `run_id`, monotonic `seq`, and ISO `ts`.
- Preserve the existing in-memory `events: list | None` path unchanged for back-compat with existing tests.
- Narrow the `reason` parameter of `_emit_plan_event` to `Literal["initial", "replan"]`, removing the `# type: ignore[arg-type]` comment.
- TDD: failing test before implementation.

**Non-Goals:**
- Wiring any other event kinds (`ObservationEvent`, `DecisionEvent`, etc.) to `loop()` — this change is scoped to `PlanEvent` only.
- Changing `TraceWriter`, `PlanEvent`, or any other trace schema models.
- Changing `eval/runner.py` beyond passing the `TraceWriter` to `loop()`.
- Introducing a new abstraction layer (e.g. abstract emitter interface) — there are exactly two callers and we design for them.

## Decisions

### Decision: Add `trace_writer: TraceWriter | None = None` parameter to `loop()`

The simplest approach is a direct optional keyword argument. The alternative (a separate `emit_plan` callable) introduces an abstraction for a hypothetical third caller that doesn't exist. The two callers (in-memory test path, `api/server.py`) map cleanly to `trace_writer=None` and `trace_writer=<writer>` respectively.

`_emit_plan_event` is updated to accept either path; internally it dispatches on which argument is provided. The constraint is: no double-emit. If both `events` and `trace_writer` are supplied, `trace_writer` takes priority (test back-compat tests never supply both simultaneously, so this is an edge case, but the spec must be deterministic).

### Decision: `seq` and `ts` assigned at call time inside `_emit_plan_event`

`TraceWriter.append_event()` validates that `seq` is strictly greater than the last persisted seq. To get the next valid `seq`, the loop must query `TraceWriter` or maintain a local counter. The simpler design: maintain a local `_seq` counter inside `loop()` that increments each time any event is written through the writer. This avoids a round-trip query to SQLite and keeps the loop free of `SELECT` calls.

`ts` is assigned as `datetime.now(UTC).isoformat()` at emit time, matching the pattern used elsewhere in `api/server.py`.

### Decision: `reason` typed as `Literal["initial", "replan"]`

The `PlanEvent` model already has `reason: Literal["initial", "replan"]`. The `# type: ignore[arg-type]` comment exists because `_emit_plan_event` accepts `str`. Narrowing the parameter type removes the ignore comment without any runtime change.

### Decision: In-memory path is unchanged; no double-emit

When `trace_writer` is provided, events go to the writer only. When `events` list is provided (and no writer), events go to the list only. This matches the two real use-cases and avoids surprising side effects in tests.

## Risks / Trade-offs

- [Risk] If `api/server.py` (or `eval/runner.py`) passes the `trace_writer` but forgets to call `open_run` first, `append_event` will raise `LookupError`. Mitigation: existing integration tests and the `_run_agent` function already call `open_run` before any append — the wiring in `_run_agent` needs to pass `run_id` and the open writer to `loop()`.
- [Risk] The local `_seq` counter in `loop()` will conflict if the writer already has events at higher seqs from a previous session for the same `run_id`. Mitigation: per the `TraceWriter` spec, a `run_id` is opened once per run and closed after. The counter starts at 1 for the first event.
- [Trade-off] Using a local seq counter means `loop()` is now the sole owner of seq for plan events. Other callers that append to the same writer (e.g. for observation events) would need to coordinate. Mitigation: in the current codebase, `loop()` is the only code path that appends events within a run; this trade-off is acceptable.

## Open Questions

None. The two callers are fully identified and the behavior is unambiguous.
