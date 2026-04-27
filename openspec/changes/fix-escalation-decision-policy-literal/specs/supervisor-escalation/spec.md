## MODIFIED Requirements

### Requirement: Supervisor module and EscalationDecision type

The system SHALL provide `agent.supervisor.Supervisor` — a stateful failure-classifier and recovery-policy module for the locator pipeline. `Supervisor` SHALL be constructible via `Supervisor(*, max_attempts: int = 3)`. The constructor SHALL accept a `max_attempts` keyword argument (default 3) representing the per-strategy attempt ceiling; it SHALL have no other required parameters and SHALL NOT perform I/O or read environment variables.

The system SHALL also provide `agent.supervisor.EscalationDecision` — a frozen dataclass with the fields:
- `next_tier: str | None` — the tier to attempt next (`"L2_dom"`, `"L3_rerank"`, `"L4_vision"`, or `None` meaning the supervisor has decided to halt).
- `policy: EscalationPolicy` — the recovery policy label, typed as the shared `EscalationPolicy` alias imported from `agent.trace`. SHALL be `"next_tier"` when `next_tier` is not `None`, and `"halt"` when `next_tier` is `None`. All values SHALL be members of `Literal["next_tier", "rerank", "sweep_overlay", "replan", "halt"]`.
- `attempt: int` — the attempt number (1-based) within the current strategy path, as tracked by the supervisor.

`EscalationDecision` SHALL be frozen so callers cannot mutate it after construction.

`Supervisor.last_policy` SHALL be typed `EscalationPolicy | None` (initially `None`), narrowed from `str | None`.

The `EscalationPolicy` alias SHALL be defined in `agent.trace` as `Literal["next_tier", "rerank", "sweep_overlay", "replan", "halt"]` and imported by `agent.supervisor`. This is the single source of truth for allowed policy values.

A mypy or pyright run on `agent/loop.py` SHALL produce no `arg-type` suppression comment on the `policy=decision.policy` assignment in `_emit_supervisor_event`. The `# type: ignore[arg-type]` comment at that line SHALL be absent.

#### Scenario: Supervisor is constructible with default arguments

- **WHEN** code constructs `Supervisor()` with no arguments
- **THEN** the construction SHALL succeed without raising
- **AND** the instance SHALL be ready to handle a `LocatorMiss`

#### Scenario: EscalationDecision is a frozen dataclass

- **WHEN** code constructs `EscalationDecision(next_tier="L2_dom", policy="next_tier", attempt=1)`
- **THEN** the construction SHALL succeed
- **AND** attempting to assign to any field SHALL raise `dataclasses.FrozenInstanceError`

#### Scenario: EscalationDecision.policy accepts only EscalationPolicy values at type-check time

- **WHEN** a static type checker analyzes `EscalationDecision(next_tier=None, policy="halt", attempt=1)`
- **THEN** the checker SHALL accept the expression without error
- **AND** `EscalationDecision(next_tier=None, policy="unknown_policy", attempt=1)` SHALL be flagged as a type error by the checker (the literal `"unknown_policy"` is not assignable to `EscalationPolicy`)

#### Scenario: Supervisor.last_policy is typed EscalationPolicy | None

- **WHEN** static analysis inspects `Supervisor.last_policy`
- **THEN** its inferred type SHALL be `EscalationPolicy | None`, not `str | None`
- **AND** assigning `supervisor.last_policy = "halt"` SHALL be accepted
- **AND** assigning `supervisor.last_policy = "unknown_policy"` SHALL be a type error

#### Scenario: EscalationPolicy alias is importable from agent.trace

- **WHEN** code executes `from agent.trace import EscalationPolicy`
- **THEN** the import SHALL succeed
- **AND** `EscalationPolicy` SHALL be a `typing.Literal` type alias with members `"next_tier"`, `"rerank"`, `"sweep_overlay"`, `"replan"`, `"halt"`

## MODIFIED Requirements

### Requirement: Supervisor exposes last_policy attribute for replan detection

`Supervisor` SHALL expose a `last_policy: EscalationPolicy | None` attribute (initially `None`) that is updated to the `policy` of the most recent `EscalationDecision` returned by `handle()`. This allows `loop.py` to read `supervisor.last_policy == "halt"` after a locate dispatch without re-examining the `EscalationDecision` return value out-of-band. The attribute type SHALL use the `EscalationPolicy` alias (not plain `str`).

#### Scenario: last_policy is None before any handle() call

- **WHEN** a `Supervisor()` is freshly constructed
- **THEN** `supervisor.last_policy` SHALL be `None`

#### Scenario: last_policy reflects the most recent policy after handle()

- **GIVEN** a `Supervisor()` and a `LocatorMiss(reason="zero_matches", match_count=0)`
- **WHEN** `supervisor.handle(miss, current_tier="L1_ax")` is called (which returns `policy="next_tier"`)
- **THEN** `supervisor.last_policy` SHALL equal `"next_tier"`

#### Scenario: last_policy is "halt" after exhaustion

- **GIVEN** a `Supervisor(max_attempts=1)` and a `LocatorMiss(reason="zero_matches", match_count=0)`
- **WHEN** `supervisor.handle(miss, current_tier="L1_ax")` is called twice (first returns `next_tier`, second cap triggers halt)
- **THEN** after the second call `supervisor.last_policy` SHALL equal `"halt"`
