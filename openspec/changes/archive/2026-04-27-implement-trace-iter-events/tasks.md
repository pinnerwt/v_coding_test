## 1. Red — empty-run iterator test

- [x] 1.1 In `task2/tests/agent/test_trace.py`, add `test_iter_events_empty_run_returns_empty_iterator`: open a run with no events appended, call `list(writer.iter_events(run_id))`, assert result equals `[]` with no exception raised.
- [x] 1.2 Add `test_iter_events_unknown_run_id_returns_empty_iterator`: create a `TraceWriter` with no runs opened, call `list(writer.iter_events("never-opened-run"))`, assert result equals `[]` with no exception.
- [x] 1.3 Run `uv run pytest task2/tests/agent/test_trace.py -k "iter_events"` from `task2/` — confirm both tests fail with `AttributeError` (method does not exist yet).

## 2. Red — N events in seq order test

- [x] 2.1 Add `test_iter_events_yields_n_events_in_seq_order`: open a run, append a `PlanEvent` at seq=1, `LocateEvent` at seq=2, `SupervisorEvent` at seq=3; assert `list(writer.iter_events(run_id))` returns 3 items with correct types and `seq` values in order.
- [x] 2.2 Add `test_iter_events_types_match_any_event_adapter`: for the same 3 events, compare `iter_events` output element-by-element against `[_any_event_adapter.validate_json(row[0]) for row in raw_sql_rows]` — assert equality.
- [x] 2.3 Add `test_iter_events_on_closed_writer_raises`: close the writer, then call and iterate `iter_events`; assert `sqlite3.ProgrammingError` is raised.
- [x] 2.4 Add `test_iter_events_on_closed_run_still_yields`: open a run, append 2 events, call `close_run`, then call `list(writer.iter_events(run_id))`; assert 2 events are returned.
- [x] 2.5 Run all new `iter_events` tests — confirm they all fail (method still does not exist).

## 3. Green — implement TraceWriter.iter_events

- [x] 3.1 In `task2/agent/trace.py`, add the SQL constant `_SELECT_EVENTS_SQL = "SELECT payload FROM traces_events WHERE run_id = ? ORDER BY seq"` near the other SQL constants.
- [x] 3.2 Add `iter_events(self, run_id: str) -> Iterator[AnyEvent]` method to `TraceWriter`: call `_require_conn()`, execute `_SELECT_EVENTS_SQL`, yield `_any_event_adapter.validate_json(row[0])` for each row.
- [x] 3.3 Add `from collections.abc import Iterator` to the imports in `agent/trace.py` (or use `typing.Iterator` if Python < 3.9 compat is needed — `from __future__ import annotations` is already present so `collections.abc.Iterator` is fine).
- [x] 3.4 Run `uv run pytest task2/tests/agent/test_trace.py -k "iter_events"` — confirm all `iter_events` tests pass.
- [x] 3.5 Run `uv run pytest task2/tests/agent/test_trace.py` — confirm no regressions in existing trace tests.
- [x] 3.6 Run `uv run ruff check task2/agent/trace.py` — confirm clean.

## 4. Refactor — switch _aggregate_diagnostics to iter_events

- [x] 4.1 In `task2/scripts/eval.py`, remove `_any_event_adapter` from the `from agent.trace import (...)` block.
- [x] 4.2 Replace the raw SQL block in `_aggregate_diagnostics` (the `writer._require_conn().execute(...)` call and the `_any_event_adapter.validate_json` list comprehension) with `events: list[AnyEvent] = list(writer.iter_events(run_id))`.
- [x] 4.3 Run `uv run pytest task2/tests/test_eval.py` — confirm all existing `_aggregate_diagnostics` tests (`test_aggregate_diagnostics_escalation_from_supervisor_event`, `test_aggregate_diagnostics_counts_replan`, `test_aggregate_diagnostics_cache_events`, `test_aggregate_diagnostics_escalation_to_tier_scoped_to_step_id`) still pass.
- [x] 4.4 Run the full test suite `uv run pytest task2/` — confirm green bar.

## 5. Cleanup and verification

- [x] 5.1 Run `grep -n "_any_event_adapter" task2/scripts/eval.py` — assert zero matches (import is gone).
- [x] 5.2 Run `grep -n "_any_event_adapter" task2/agent/trace.py` — confirm it still appears only inside `agent/trace.py` (private, not exported).
- [x] 5.3 Run `uv run ruff check task2/scripts/eval.py` — confirm clean.
- [x] 5.4 Run `uv run ruff format task2/` and confirm no diff (or apply formatting and re-check).
- [x] 5.5 Run full test suite one final time: `uv run pytest task2/` — confirm green.
