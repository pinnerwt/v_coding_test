## MODIFIED Requirements

### Requirement: SupervisorEvent model

The system SHALL provide `agent.trace.SupervisorEvent(EventBase)` with `kind: Literal["supervisor"]` and:

- `trigger_event_seq: int` — `seq` of the Act or Locate event that triggered supervisor escalation. For `classified_as="premature_fail"` events emitted without a prior Locate or Act event, this MAY be set to `0`.
- `classified_as: Literal["LocatorMiss","Ambiguous","NoEffect","FormError","NavDrift","Blocked","Timeout","premature_fail"]`.
- `policy: Literal["next_tier","rerank","sweep_overlay","replan","halt"]`.
- `attempt: int` — position in the strategy ladder (1..N).

#### Scenario: SupervisorEvent round-trips through JSON

- **WHEN** a `SupervisorEvent` is serialized and deserialized
- **THEN** the result SHALL equal the original

#### Scenario: SupervisorEvent accepts premature_fail as classified_as value

- **WHEN** a `SupervisorEvent` is constructed with `classified_as="premature_fail"`
- **THEN** Pydantic validation SHALL succeed (no `ValidationError`)
- **AND** the serialized JSON SHALL contain `"classified_as": "premature_fail"`
