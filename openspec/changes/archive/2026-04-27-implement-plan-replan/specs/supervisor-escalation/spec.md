## ADDED Requirements

### Requirement: Supervisor exposes last_policy attribute for replan detection

`Supervisor` SHALL expose a `last_policy: str | None` attribute (initially `None`) that is updated to the `policy` string of the most recent `EscalationDecision` returned by `handle()`. This allows `loop.py` to read `supervisor.last_policy == "halt"` after a locate dispatch without re-examining the `EscalationDecision` return value out-of-band.

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
