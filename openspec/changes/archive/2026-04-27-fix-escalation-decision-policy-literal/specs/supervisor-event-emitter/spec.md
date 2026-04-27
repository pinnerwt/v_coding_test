## MODIFIED Requirements

### Requirement: _emit_supervisor_event helper in loop.py

The system SHALL provide a private helper `_emit_supervisor_event` in `agent/loop.py` with the signature:

```python
def _emit_supervisor_event(
    *,
    trace_writer: TraceWriter | None,
    run_id: str | None,
    decision: EscalationDecision,
    miss: LocatorMiss,
    trigger_event_seq: int,
    step_id: str | None = None,
) -> None:
```

When `trace_writer` is `None` or `run_id` is `None`, the helper SHALL be a no-op (return immediately without side effects).

Otherwise, it SHALL:
1. Map `miss.reason` to `classified_as` using the following table: `"zero_matches"` → `"LocatorMiss"`, `"ambiguous"` → `"Ambiguous"`, `"vision_miss"` → `"LocatorMiss"`. Any unrecognised reason SHALL map to `"LocatorMiss"`.
2. Allocate a sequence number via `trace_writer.next_seq(run_id)`.
3. Construct a `SupervisorEvent` with `policy=decision.policy`, `attempt=decision.attempt`, `classified_as=<mapped value>`, `trigger_event_seq=trigger_event_seq`, `step_id=step_id`, and a valid ISO `ts`.
4. Call `trace_writer.append_event(event)`.

Because `EscalationDecision.policy` is now typed `EscalationPolicy` (the same `Literal` as `SupervisorEvent.policy`), the assignment `policy=decision.policy` SHALL be accepted by a static type checker without any `# type: ignore` comment. The `# type: ignore[arg-type]` suppression that previously appeared on that line SHALL be absent from the codebase.

#### Scenario: _emit_supervisor_event is a no-op when trace_writer is None

- **WHEN** `_emit_supervisor_event(trace_writer=None, run_id=None, decision=..., miss=..., trigger_event_seq=1, step_id=None)` is called
- **THEN** it SHALL return without raising and without writing any event

#### Scenario: _emit_supervisor_event writes SupervisorEvent with correct fields

- **GIVEN** an open `TraceWriter` with `run_id` and one prior event at seq=1
- **WHEN** `_emit_supervisor_event(trace_writer=writer, run_id=run_id, decision=EscalationDecision(next_tier="L2_dom", policy="next_tier", attempt=1), miss=LocatorMiss(reason="zero_matches", match_count=0), trigger_event_seq=1, step_id="r:step-2")` is called
- **THEN** the writer SHALL contain a new `SupervisorEvent` at seq=2
- **AND** `event.policy` SHALL equal `"next_tier"`
- **AND** `event.classified_as` SHALL equal `"LocatorMiss"`
- **AND** `event.trigger_event_seq` SHALL equal `1`
- **AND** `event.attempt` SHALL equal `1`
- **AND** `event.step_id` SHALL equal `"r:step-2"`

#### Scenario: _emit_supervisor_event maps ambiguous reason to Ambiguous

- **GIVEN** an open `TraceWriter` with `run_id`
- **WHEN** `_emit_supervisor_event(..., miss=LocatorMiss(reason="ambiguous", match_count=3), ...)` is called
- **THEN** the written `SupervisorEvent.classified_as` SHALL equal `"Ambiguous"`

#### Scenario: No type: ignore comment on policy assignment

- **WHEN** a static type checker (mypy or pyright) analyzes `agent/loop.py`
- **THEN** the line `policy=decision.policy` in `_emit_supervisor_event` SHALL produce no `arg-type` or equivalent suppression warning
- **AND** the source file SHALL contain no `# type: ignore[arg-type]` comment on that line
