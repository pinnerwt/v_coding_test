## ADDED Requirements

### Requirement: TraceWriter.iter_events public method

`agent.trace.TraceWriter` SHALL expose a public method `iter_events(run_id: str) -> Iterator[AnyEvent]` that:

1. Calls `_require_conn()` to obtain the SQLite connection (raising `sqlite3.ProgrammingError` if the writer is closed, consistent with all other `TraceWriter` methods).
2. Issues `SELECT payload FROM traces_events WHERE run_id = ? ORDER BY seq` against the connection.
3. Yields each row's payload deserialised via `_any_event_adapter.validate_json(payload)` — the same private adapter and parsing path already used in `append_event`.
4. Yields events in strictly increasing `seq` order (guaranteed by `ORDER BY seq`).
5. Returns an empty iterator (yields nothing, raises no error) when `run_id` has no rows in `traces_events` — whether because the run was never opened, was opened but has no events appended, or `run_id` is completely unknown.

`iter_events` SHALL NOT check `traces_runs.status`; it is valid to call it on a closed run to iterate post-run events.

The method SHALL be a generator (uses `yield`) so events are not all loaded into memory at once.

#### Scenario: iter_events on a writer with no events for the run returns empty iterator

- **GIVEN** a `TraceWriter` opened with `:memory:` and a run opened via `open_run(run)` with no events appended
- **WHEN** `list(writer.iter_events(run_id))` is called
- **THEN** the result SHALL equal `[]`
- **AND** no exception SHALL be raised

#### Scenario: iter_events on a completely unknown run_id returns empty iterator

- **GIVEN** a `TraceWriter` opened with `:memory:` with no runs opened
- **WHEN** `list(writer.iter_events("never-opened-run"))` is called
- **THEN** the result SHALL equal `[]`
- **AND** no exception SHALL be raised

#### Scenario: iter_events yields N events in seq order with correct Pydantic types

- **GIVEN** a `TraceWriter` opened with `:memory:` and a run opened via `open_run(run)`
- **AND** events of mixed kinds appended: a `PlanEvent` at seq=1, a `LocateEvent` at seq=2, a `SupervisorEvent` at seq=3
- **WHEN** `list(writer.iter_events(run_id))` is called
- **THEN** the result SHALL contain exactly 3 elements
- **AND** element 0 SHALL be an instance of `PlanEvent` with `seq == 1`
- **AND** element 1 SHALL be an instance of `LocateEvent` with `seq == 2`
- **AND** element 2 SHALL be an instance of `SupervisorEvent` with `seq == 3`

#### Scenario: iter_events yields events identical to _any_event_adapter.validate_json output

- **GIVEN** a `TraceWriter` with N appended events of varied kinds
- **WHEN** `list(writer.iter_events(run_id))` is called
- **AND** the same event rows are fetched via raw SQL and deserialised with `_any_event_adapter.validate_json`
- **THEN** both lists SHALL be equal element-by-element

#### Scenario: iter_events on a closed TraceWriter raises ProgrammingError

- **GIVEN** a `TraceWriter` that has been closed via `writer.close()`
- **WHEN** `writer.iter_events(run_id)` is called (without iterating)
- **THEN** `sqlite3.ProgrammingError` SHALL be raised

#### Scenario: iter_events on a closed run still yields events

- **GIVEN** a `TraceWriter` with a run that has been opened, had 2 events appended, and then closed via `close_run(...)`
- **WHEN** `list(writer.iter_events(run_id))` is called
- **THEN** the result SHALL contain exactly 2 elements in seq order
