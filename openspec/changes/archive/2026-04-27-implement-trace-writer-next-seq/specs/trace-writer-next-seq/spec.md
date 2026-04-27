## ADDED Requirements

### Requirement: TraceWriter.next_seq returns the next valid seq for a run

The system SHALL provide `TraceWriter.next_seq(run_id: str) -> int` — a public method that queries `MAX(seq)` from `traces_events` for the given `run_id` and returns `MAX(seq) + 1`. If no events have been appended yet for that run, it SHALL return `1`. The run MUST be open (present in `traces_runs` and not closed); if the `run_id` is not found or the run is already closed, `LookupError` SHALL be raised. The returned value is guaranteed to satisfy `> MAX(seq)` at the moment of the query, making it safe to pass directly to `append_event` as `event.seq` in a single-threaded context.

#### Scenario: next_seq on a freshly opened run returns 1

- **GIVEN** a `TraceWriter` opened in `:memory:`
- **AND** `open_run(run)` has been called for `run_id="r1"` with no events appended
- **WHEN** `next_seq("r1")` is called
- **THEN** it SHALL return `1`

#### Scenario: next_seq after one event returns N+1

- **GIVEN** a `TraceWriter` opened in `:memory:` with a run at `run_id="r1"`
- **AND** one event with `seq=1` has been appended via `append_event`
- **WHEN** `next_seq("r1")` is called
- **THEN** it SHALL return `2`

#### Scenario: next_seq after three events returns 4

- **GIVEN** a `TraceWriter` opened in `:memory:` with a run at `run_id="r1"`
- **AND** events with seq=1, seq=2, seq=3 have been appended
- **WHEN** `next_seq("r1")` is called
- **THEN** it SHALL return `4`

#### Scenario: next_seq raises LookupError for unknown run_id

- **GIVEN** a `TraceWriter` opened in `:memory:` with no runs opened
- **WHEN** `next_seq("does-not-exist")` is called
- **THEN** a `LookupError` SHALL be raised

#### Scenario: next_seq raises LookupError for a closed run

- **GIVEN** a `TraceWriter` opened in `:memory:` with a run that has been closed via `close_run`
- **WHEN** `next_seq(run_id)` is called for that run
- **THEN** a `LookupError` SHALL be raised

#### Scenario: two interleaved emitters produce strictly increasing seq with no SeqError

- **GIVEN** a `TraceWriter` opened in `:memory:` with `run_id="r-interleave"`
- **AND** `loop()` is called with `trace_writer=writer` and `run_id="r-interleave"`, using a mock browser and LLM that causes the loop to emit one initial `PlanEvent` and then terminate
- **WHEN** the test appends a manually-constructed `ObservationEvent` using `seq=writer.next_seq("r-interleave")` after `loop()` returns
- **THEN** both `append_event` calls SHALL succeed without raising `SeqError`
- **AND** the `traces_events` table SHALL contain both rows with strictly increasing `seq` values (plan event seq < observation event seq)
