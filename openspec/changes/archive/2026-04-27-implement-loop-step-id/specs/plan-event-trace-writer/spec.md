## MODIFIED Requirements

### Requirement: loop() accepts optional TraceWriter for plan event persistence

The `loop()` function in `agent.loop` SHALL accept an optional keyword argument `trace_writer: TraceWriter | None = None`. When `trace_writer` is not `None`, `PlanEvent` rows SHALL be written through it with:

- `run_id` matching the run opened in the `TraceWriter` (passed by the caller, e.g. `api/server.py`).
- `seq` obtained by calling `trace_writer.next_seq(run_id)` immediately before constructing the event, so the value is always strictly greater than the last persisted seq regardless of how many other events have been appended by any emitter.
- `ts` set to `datetime.now(UTC).isoformat()` at the moment of emission.
- **`step_id` set to `f"{run_id}:step-{step_num}"` where `step_num` is the loop's current 1-indexed step counter** (i.e. the step during which the plan or replan was triggered). This replaces the previous hardcoded `step_id=None`.

When `trace_writer` is `None`, plan event persistence falls back to the in-memory `events: list | None` path (existing behavior), and the `step_id` is populated the same way if `run_id` is not `None`.

No double-emit SHALL occur: if `trace_writer` is provided, plan events SHALL NOT also be appended to the `events` list.

The `loop()` function SHALL NOT maintain a local `plan_seq` counter. All seq assignment for TraceWriter-backed plan events SHALL go through `next_seq()`.

The internal helper `_emit_plan_event` SHALL NOT accept a `seq` parameter. It SHALL call `trace_writer.next_seq(run_id)` internally when `trace_writer` is provided. It SHALL accept a `step_id: str | None` parameter and forward it to the `PlanEvent` constructor.

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

#### Scenario: initial PlanEvent has step_id matching step 1

- **GIVEN** a `TraceWriter` opened in `:memory:` with `run_id="test-run-4"`
- **AND** `loop()` is called with `trace_writer=writer` and `run_id="test-run-4"`
- **WHEN** the loop completes
- **THEN** the `kind="plan"` row with `reason="initial"` SHALL have `step_id="test-run-4:step-1"`

#### Scenario: replan PlanEvent has step_id matching the halt step

- **GIVEN** a `TraceWriter` opened in `:memory:` with `run_id="test-run-5"`
- **AND** `loop()` triggers a replan via supervisor halt on step 2
- **WHEN** the loop completes
- **THEN** the `kind="plan"` row with `reason="replan"` SHALL have `step_id="test-run-5:step-2"`

#### Scenario: plan events have strictly increasing seq

- **GIVEN** a `TraceWriter` opened in `:memory:` with a given `run_id`
- **AND** `loop()` is called with `trace_writer=writer`
- **WHEN** the loop emits one or more plan events
- **THEN** all `kind="plan"` rows in `traces_events` for that `run_id` SHALL have strictly increasing `seq` values
- **AND** the first plan event SHALL have `seq >= 1`

Note: cross-kind ordering between plan and decision/observation events is intentionally out of scope here; decision-event persistence through `TraceWriter` is tracked under `task2/plan.md` ticket #20.

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
