## Why

`_aggregate_diagnostics` in `scripts/eval.py` currently bypasses `TraceWriter`'s public API: it calls `writer._require_conn().execute(...)` directly and imports the private `_any_event_adapter` symbol from `agent.trace` to deserialise event rows. This couples the eval runner to storage internals (table name, column layout, adapter symbol path) so that renaming, resharding, or swapping the backend would silently break the eval without any type-system or import-boundary signal.

## What Changes

- **New public method** `TraceWriter.iter_events(run_id: str) -> Iterator[AnyEvent]` added to `agent.trace.TraceWriter`: yields parsed events in strictly increasing `seq` order for the given run, using the same `_any_event_adapter` parsing path already used internally.
- **Refactor** `_aggregate_diagnostics` in `scripts/eval.py` to iterate over `writer.iter_events(run_id)` instead of issuing raw SQL and calling `_any_event_adapter.validate_json` directly.
- **Import cleanup**: `from agent.trace import _any_event_adapter` is removed from `scripts/eval.py`; `_any_event_adapter` remains private to `agent/trace.py`.

## Capabilities

### New Capabilities

- `trace-writer-iter-events`: Public `TraceWriter.iter_events(run_id)` method that yields all events for a run in `seq` order as typed Pydantic models.

### Modified Capabilities

- `eval-proof-metrics`: `_aggregate_diagnostics` requirement updates — the implementation detail of how it fetches and parses events changes (public iterator replaces raw SQL + private adapter), but the observable behaviour (returned tuple shape and values) is unchanged.

## Impact

- `task2/agent/trace.py` — gains `iter_events` method (public surface expansion).
- `task2/scripts/eval.py` — removes direct SQL call and `_any_event_adapter` import in `_aggregate_diagnostics`.
- `task2/tests/agent/test_trace.py` — new tests for `iter_events`.
- `task2/tests/test_eval.py` — all existing `_aggregate_diagnostics` tests must remain green; no new test fixtures needed there beyond confirming the import is gone.
- No schema changes, no dependency additions, no Zeabur impact.
