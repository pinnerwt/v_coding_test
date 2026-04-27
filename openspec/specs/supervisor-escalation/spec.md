# supervisor-escalation Specification

## Purpose
TBD - created by archiving change implement-supervisor. Update Purpose after archive.
## Requirements
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

### Requirement: Supervisor.handle classifies LocatorMiss and returns EscalationDecision

`Supervisor.handle(self, miss: LocatorMiss, *, current_tier: str) -> EscalationDecision` SHALL accept a `LocatorMiss` instance and the string name of the tier that raised it, and SHALL return an `EscalationDecision` according to the escalation table:

| `current_tier` | `miss.reason`    | `next_tier`   | `policy`      |
|---|---|---|---|
| `"L1_ax"`      | `"zero_matches"` | `"L2_dom"`    | `"next_tier"` |
| any            | `"vision_miss"`  | `None`        | `"halt"`      |
| any (unrecognised combination) | any | `None` | `"halt"` |

`L1_ax` / `ambiguous` → `L3_rerank`, `L2_dom` → escalation, and `L3_rerank` → escalation rows ARE NOT part of this change and SHALL NOT be implemented. `handle()` SHALL return `EscalationDecision(next_tier=None, policy="halt", attempt=1)` for any `(current_tier, miss.reason)` pair not in the implemented table above.

`handle()` SHALL increment the supervisor's internal attempt counter for the observed `(current_tier, miss.reason)` pair. When the attempt count exceeds `max_attempts`, `handle()` SHALL return `EscalationDecision(next_tier=None, policy="halt", attempt=<current_count>)` regardless of the escalation table, so callers are protected against infinite escalation loops.

#### Scenario: L1 zero-match miss escalates to L2

- **GIVEN** a `Supervisor()` with default `max_attempts`
- **AND** a `LocatorMiss(reason="zero_matches", match_count=0)`
- **WHEN** `supervisor.handle(miss, current_tier="L1_ax")` is called
- **THEN** the returned `EscalationDecision.next_tier` SHALL equal `"L2_dom"`
- **AND** the returned `EscalationDecision.policy` SHALL equal `"next_tier"`
- **AND** the returned `EscalationDecision.attempt` SHALL equal `1`

#### Scenario: vision_miss from any tier halts

- **GIVEN** a `Supervisor()` with default `max_attempts`
- **AND** a `LocatorMiss(reason="vision_miss", match_count=0)`
- **WHEN** `supervisor.handle(miss, current_tier="L4_vision")` is called
- **THEN** the returned `EscalationDecision.next_tier` SHALL be `None`
- **AND** the returned `EscalationDecision.policy` SHALL equal `"halt"`

#### Scenario: Unrecognised tier+reason combination halts

- **GIVEN** a `Supervisor()` with default `max_attempts`
- **AND** a `LocatorMiss(reason="zero_matches", match_count=0)`
- **WHEN** `supervisor.handle(miss, current_tier="L2_dom")` is called (L2 escalation not yet implemented)
- **THEN** the returned `EscalationDecision.next_tier` SHALL be `None`
- **AND** the returned `EscalationDecision.policy` SHALL equal `"halt"`

#### Scenario: Attempt counter increments across repeated calls

- **GIVEN** a `Supervisor()` with default `max_attempts`
- **AND** a `LocatorMiss(reason="zero_matches", match_count=0)`
- **WHEN** `supervisor.handle(miss, current_tier="L1_ax")` is called twice in succession
- **THEN** the first call SHALL return `EscalationDecision(next_tier="L2_dom", policy="next_tier", attempt=1)`
- **AND** the second call SHALL return `EscalationDecision(next_tier="L2_dom", policy="next_tier", attempt=2)`

#### Scenario: Attempt cap triggers halt

- **GIVEN** a `Supervisor(max_attempts=2)`
- **AND** a `LocatorMiss(reason="zero_matches", match_count=0)`
- **WHEN** `supervisor.handle(miss, current_tier="L1_ax")` is called three times
- **THEN** the first two calls SHALL return decisions with `policy="next_tier"`
- **AND** the third call SHALL return `EscalationDecision(next_tier=None, policy="halt", attempt=3)`

### Requirement: End-to-end escalation: L1 miss → supervisor decision → L2 success

When a page causes `locate_l1` to raise `LocatorMiss(reason="zero_matches")`, the supervisor SHALL return a decision pointing at `"L2_dom"`, and executing `locate_l2` against the same page with the same `(role, name)` parameters SHALL succeed (returning a `LocateResult` with `tier="L2_dom"`), provided the page exposes an element reachable by L2 DOM heuristics.

This requirement validates the composition of `Supervisor.handle()` with `locate_l2` — it is the acceptance criterion for ticket #8.

#### Scenario: Synthetic L1 miss → supervisor escalates → L2 succeeds on compatible fixture

- **GIVEN** a page that has no accessible element matching `role=textbox name="Email address"` (so L1 raises `LocatorMiss(reason="zero_matches", match_count=0)`)
- **AND** the page contains exactly one `<input placeholder="Email address">` (so L2 via placeholder succeeds)
- **AND** a `Supervisor()` instance
- **WHEN** `supervisor.handle(LocatorMiss(reason="zero_matches", match_count=0), current_tier="L1_ax")` is called
- **THEN** the decision SHALL have `next_tier="L2_dom"` and `policy="next_tier"`
- **AND** calling `locate_l2(page, role="textbox", name="Email address")` SHALL return a `LocateResult` with `tier="L2_dom"`

#### Scenario: Supervisor does not call the browser itself

- **GIVEN** a `Supervisor()` instance
- **WHEN** `supervisor.handle(LocatorMiss(reason="zero_matches", match_count=0), current_tier="L1_ax")` is called without a `page` argument
- **THEN** the call SHALL succeed (the supervisor does not accept or use a `page` object)
- **AND** no Playwright call SHALL have been made

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

### Requirement: Supervisor exposes replan_used flag

`Supervisor` SHALL expose a `replan_used: bool` attribute (initially `False`). When `loop.py` performs a replan in response to a halt, it SHALL set `supervisor.replan_used = True`. On the next halt, `loop.py` checks `supervisor.replan_used` to determine that the replan budget is exhausted and the halt is terminal.

`Supervisor.handle()` itself SHALL NOT set `replan_used`; only `loop.py` sets it. This keeps the supervisor's existing test surface unchanged.

#### Scenario: replan_used is False on construction

- **WHEN** a `Supervisor()` is freshly constructed
- **THEN** `supervisor.replan_used` SHALL be `False`

#### Scenario: loop.py sets replan_used to True after performing a replan

- **GIVEN** a run where the first supervisor halt triggers a replan
- **WHEN** the replan completes and the loop continues
- **THEN** `supervisor.replan_used` SHALL be `True`

#### Scenario: replan_used True causes second halt to be terminal

- **GIVEN** a `Supervisor` where `replan_used` has been set to `True`
- **WHEN** `supervisor.last_policy == "halt"` again on a subsequent step
- **THEN** the loop SHALL treat it as a terminal failure without calling `replan()`
