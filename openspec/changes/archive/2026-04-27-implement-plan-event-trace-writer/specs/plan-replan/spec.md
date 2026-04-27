## MODIFIED Requirements

### Requirement: plan.py has no comments or docstrings

The production file `task2/agent/plan.py` SHALL contain zero module-level, function-level, or inline comments (except single-line `# why` comments for non-obvious constraints). It SHALL contain zero docstrings.

#### Scenario: plan.py source passes the no-docstring constraint

- **WHEN** `task2/agent/plan.py` is inspected
- **THEN** it SHALL contain no `"""` or `'''` docstring literals at the module, class, or function level
- **AND** ruff format and ruff check SHALL both exit 0

## ADDED Requirements

### Requirement: in-memory events list preserves PlanEvent back-compat after TraceWriter wiring

After the TraceWriter wiring is introduced in `loop()`, existing tests that pass an `events: list` without a `trace_writer` SHALL continue to receive `PlanEvent` objects in the list in the correct order (initial plan before first decision, replan before next decision after supervisor halt).

#### Scenario: in-memory events list still captures initial plan event

- **GIVEN** `loop()` is called with `events=[]` and no `trace_writer`
- **WHEN** the loop runs and the initial plan is generated
- **THEN** the `events` list SHALL contain an entry with `kind="plan"` and `reason="initial"`
- **AND** it SHALL appear before any entry with `kind="decision"`

#### Scenario: in-memory events list still captures replan event

- **GIVEN** `loop()` is called with `events=[]` and no `trace_writer`
- **AND** the loop triggers a replan via supervisor halt
- **WHEN** the replan is generated
- **THEN** the `events` list SHALL contain an entry with `kind="plan"` and `reason="replan"`
- **AND** it SHALL appear before the next entry with `kind="decision"` following the replan
