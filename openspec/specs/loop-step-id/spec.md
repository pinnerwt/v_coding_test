# loop-step-id Specification

## Purpose

Define the `step_id` convention for events emitted by `agent.loop.loop()` and ensure `PlanEvent` and `LocateEvent` rows carry a non-`None` `step_id` that can be used to join trace rows back to the loop step that produced them.

## Requirements

### Requirement: step_id format convention

The `step_id` field in any event emitted by `agent.loop.loop()` SHALL be formatted as `f"{run_id}:step-{step_num}"` where:

- `run_id` is the value passed to `loop()` as the `run_id` keyword argument.
- `step_num` is the loop's 1-indexed per-step counter (the same value stored in `step_breakdown[i]["step"]`).

When `loop()` is called with `run_id=None`, the `step_id` SHALL be `None` for all events emitted during that run (backward-compatible with existing in-memory test usage).

#### Scenario: step_id format with valid run_id

- **GIVEN** `loop()` is called with `run_id="abc-123"`
- **AND** the loop is on its third iteration (`step_num == 3`)
- **WHEN** a `PlanEvent` or `LocateEvent` is emitted during that step
- **THEN** the event's `step_id` field SHALL equal `"abc-123:step-3"`

#### Scenario: step_id is None when run_id is None

- **GIVEN** `loop()` is called without a `run_id` argument (or with `run_id=None`)
- **WHEN** a `PlanEvent` or `LocateEvent` is emitted
- **THEN** the event's `step_id` field SHALL be `None`

### Requirement: PlanEvent step_id matches the step that triggered the plan

The initial `PlanEvent(reason="initial")` SHALL carry the `step_id` of step 1 (i.e. `f"{run_id}:step-1"`), since planning occurs at step 1.

A `PlanEvent(reason="replan")` SHALL carry the `step_id` of the step at which the supervisor halt occurred (i.e. the `step_num` at the time the halt was detected), not a future or past step number.

#### Scenario: Initial PlanEvent step_id is step-1

- **GIVEN** `loop()` is called with `run_id="run-x"` and a `TraceWriter` open on `"run-x"`
- **WHEN** the loop runs and emits the initial plan event
- **THEN** `list(writer.iter_events("run-x"))` SHALL contain a `PlanEvent` with `reason="initial"` and `step_id="run-x:step-1"`

#### Scenario: Replan PlanEvent step_id matches the halt step

- **GIVEN** `loop()` is called with `run_id="run-y"` and a `TraceWriter` open on `"run-y"`
- **AND** the supervisor halts on step 2 (triggering a replan)
- **WHEN** the loop emits the replan plan event
- **THEN** the `PlanEvent` with `reason="replan"` SHALL have `step_id="run-y:step-2"`

### Requirement: LocateEvent step_id matches the step that triggered the locate call

Every `LocateEvent` emitted inside `_locate_with_supervisor` during step N SHALL carry `step_id = f"{run_id}:step-{N}"`.

This applies to all cache actions: read-hit (`cache_action="read"`), invalidate (`cache_action="invalidate"`), and write (`cache_action="write"`).

#### Scenario: LocateEvent cache write on step 1 carries step-1 step_id

- **GIVEN** `loop()` is called with `run_id="run-z"`, `locator_cache=<fresh cache>`, and a `TraceWriter`
- **AND** the LLM emits `read(intent="Submit button")` on step 2
- **WHEN** the locate call resolves and writes to the cache
- **THEN** the `LocateEvent` row with `cache_action="write"` SHALL have `step_id="run-z:step-2"`

#### Scenario: LocateEvent cache invalidate carries the step that triggered it

- **GIVEN** a shared `LocatorCache` warmed from a v1 run
- **AND** `loop()` runs on a v2 fixture page with `run_id="run-w"` and the cache on step 3
- **WHEN** the fingerprint mismatch causes a cache invalidation
- **THEN** the `LocateEvent` row with `cache_action="invalidate"` SHALL have `step_id="run-w:step-3"`

### Requirement: In-memory events path receives populated step_id

When `loop()` is called with an in-memory `events: list` and `run_id` is not `None`, `PlanEvent` and `LocateEvent` objects appended to that list SHALL also carry the non-`None` `step_id`. This ensures the in-memory path (used by test fixtures) and the `TraceWriter` path produce consistent event shapes.

#### Scenario: In-memory events list contains PlanEvent with step_id

- **GIVEN** `loop()` is called with `events=[]`, `run_id="test-run"`, and no `trace_writer`
- **WHEN** the loop runs
- **THEN** the `PlanEvent` appended to `events` SHALL have `step_id="test-run:step-1"`

#### Scenario: Existing in-memory test path with no run_id still receives step_id=None

- **GIVEN** `loop()` is called with `events=[]` and no `run_id` (default `None`)
- **WHEN** the loop runs
- **THEN** the `PlanEvent` in `events` SHALL have `step_id=None` (no regression from pre-change behavior)
