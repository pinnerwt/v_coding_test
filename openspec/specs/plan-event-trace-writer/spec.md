# plan-event-trace-writer Specification

## Purpose
TBD - created by archiving change implement-plan-event-trace-writer. Update Purpose after archive.
## Requirements
### Requirement: loop() accepts optional TraceWriter for plan event persistence

The `loop()` function in `agent.loop` SHALL accept an optional keyword argument `trace_writer: TraceWriter | None = None`. When `trace_writer` is not `None`, `PlanEvent` rows SHALL be written through it with:

- `run_id` matching the run opened in the `TraceWriter` (passed by the caller, e.g. `api/server.py`).
- `seq` strictly greater than the last event seq for that run, assigned by the loop's local monotonic counter starting at 1 for the first event in the run.
- `ts` set to `datetime.now(UTC).isoformat()` at the moment of emission.

When `trace_writer` is `None`, plan event persistence falls back to the in-memory `events: list | None` path (existing behavior).

No double-emit SHALL occur: if `trace_writer` is provided, plan events SHALL NOT also be appended to the `events` list.

#### Scenario: loop with TraceWriter writes plan event with real run_id

- **GIVEN** a `TraceWriter` opened in `:memory:` with `run_id="test-run-1"`
- **AND** `loop()` is called with `trace_writer=writer` and `run_id="test-run-1"`
- **WHEN** the loop completes
- **THEN** the `traces_events` table SHALL contain at least one row with `run_id="test-run-1"` and a JSON payload where `"kind": "plan"`
- **AND** the `run_id` field in that payload SHALL equal `"test-run-1"` (not `"loop"`)

#### Scenario: loop with TraceWriter writes plan event with non-zero seq

- **GIVEN** a `TraceWriter` opened in `:memory:` with `run_id="test-run-2"`
- **AND** `loop()` is called with `trace_writer=writer` and `run_id="test-run-2"`
- **WHEN** the loop completes
- **THEN** the `kind="plan"` row in `traces_events` SHALL have `seq >= 1`

#### Scenario: loop with TraceWriter writes plan event with ISO-formatted ts

- **GIVEN** a `TraceWriter` opened in `:memory:` with `run_id="test-run-3"`
- **AND** `loop()` is called with `trace_writer=writer` and `run_id="test-run-3"`
- **WHEN** the loop completes
- **THEN** the `kind="plan"` row's `ts` field SHALL be a non-empty string parseable as an ISO 8601 datetime (not an empty string)

#### Scenario: plan events have strictly increasing seq

- **GIVEN** a `TraceWriter` opened in `:memory:` with a given `run_id`
- **AND** `loop()` is called with `trace_writer=writer`
- **WHEN** the loop emits one or more plan events
- **THEN** all `kind="plan"` rows in `traces_events` for that `run_id` SHALL have strictly increasing `seq` values
- **AND** the first plan event SHALL have `seq >= 1`

Note: cross-kind ordering between plan and decision/observation events is intentionally out of scope here; decision-event persistence through `TraceWriter` is tracked under `task2/plan.md` ticket #20 and ticket #26 (`TraceWriter.next_seq(run_id)`).

#### Scenario: replan event seq is greater than initial plan event seq

- **GIVEN** a `TraceWriter` opened in `:memory:` with a given `run_id`
- **AND** `loop()` triggers a replan via supervisor halt
- **WHEN** the loop completes
- **THEN** the `traces_events` table SHALL contain a row with `kind="plan"` and `reason="replan"`
- **AND** its `seq` SHALL be strictly greater than the `seq` of the initial plan event

#### Scenario: no double-emit when trace_writer is provided

- **GIVEN** a `TraceWriter` opened in `:memory:`
- **AND** an in-memory `events` list
- **AND** `loop()` is called with both `trace_writer=writer` and `events=events`
- **WHEN** the loop completes
- **THEN** the `events` list SHALL NOT contain any `PlanEvent` objects
- **AND** the `TraceWriter` SHALL contain the plan event row

### Requirement: loop() accepts run_id parameter for trace correlation

The `loop()` function SHALL accept an optional keyword argument `run_id: str | None = None`. This value is used as the `run_id` field when constructing `PlanEvent` objects written through the `TraceWriter`. When `trace_writer` is `None`, `run_id` is ignored.

#### Scenario: run_id passed to loop is reflected in plan event payload

- **GIVEN** `run_id="my-specific-run"` is passed to `loop()`
- **AND** a `TraceWriter` is passed as `trace_writer`
- **WHEN** the loop emits a plan event
- **THEN** the plan event's `run_id` field SHALL equal `"my-specific-run"`

### Requirement: loop() rejects trace_writer without run_id

The `loop()` function SHALL raise `ValueError` when called with a non-`None` `trace_writer` and a `None` `run_id`. This prevents a silent fallback to the in-memory `events` path that would lose plan-event persistence in production callers.

#### Scenario: trace_writer without run_id raises ValueError

- **GIVEN** a `TraceWriter` opened in `:memory:`
- **WHEN** `loop()` is called with `trace_writer=writer` and no `run_id`
- **THEN** the call SHALL raise `ValueError` with a message mentioning `run_id`

### Requirement: _emit_plan_event reason parameter is Literal typed

The internal function `_emit_plan_event` in `agent.loop` SHALL have its `reason` parameter typed as `Literal["initial", "replan"]`. The existing `# type: ignore[arg-type]` comment on the calls into `PlanEvent(reason=...)` SHALL be removed. `uv run ruff check .` SHALL exit 0 after this change.

#### Scenario: ruff check passes with no type: ignore comment

- **WHEN** `uv run ruff check .` is run from the `task2/` directory after the change
- **THEN** it SHALL exit with code 0 and report no errors related to `loop.py`

### Requirement: loop.py has no comments or docstrings in production code

The production file `task2/agent/loop.py` SHALL contain zero inline comments (including `# type: ignore`) and zero docstrings after this change, consistent with the existing no-comments rule for `task2/agent/` production files.

#### Scenario: loop.py passes ruff format and ruff check after change

- **WHEN** `uv run ruff format . && uv run ruff check .` is run from `task2/`
- **THEN** both commands SHALL exit 0
