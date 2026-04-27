## ADDED Requirements

### Requirement: _classify_failure derives failure_class and failure_detail from trace

The system SHALL provide a module-level function `_classify_failure(events: list[AnyEvent], validators: list[dict], status: str) -> tuple[str | None, str | None]` in `scripts/eval.py` that:

1. Returns `(None, None)` immediately when `status` is not `"failed"`.
2. Inspects `events` and `validators` in the following priority order to determine `failure_class`:
   a. `"supervisor_halt"` — when a `SupervisorEvent(policy="halt")` is present in `events`.
   b. `"locator_miss"` — when a `SupervisorEvent(policy="next_tier")` is present in `events` AND the subsequent `LocateEvent` in the same `step_id` block has `outcome != "hit"` (all tiers exhausted without resolution).
   c. `"tool_error"` — when an `ActEvent(outcome="error")` is present in `events`.
   d. `"validator_fail"` — when a `DoneEvent` is present in `events` AND at least one dict in `validators` has `ok=False` AND the validator name does not equal `"exception"`. The `DoneEvent` requirement matches the design intent ("the agent reached `done` but the output was wrong"); without it, `_run_case` calls `run_validators` against `{}`, which spuriously trips most validators and would mis-classify a no-done case. Exception-path validators (`name="exception"`) are skipped here; the case is classified by subsequent rules in this list (typically `tool_error` from `_run_case`'s except path setting `failure_class` directly, or `other` if the trace happens to be otherwise empty).
   e. `"schema_error"` — when a `DoneEvent` is present in `events` AND `event.verifier.get("ok") is False`.
   f. `"no_done_emitted"` — when no `DoneEvent` is present in `events`.
   g. `"other"` — catch-all for any remaining `failed` status.
3. Returns `(failure_class, failure_detail)` where `failure_detail` is a short human-readable string constructed from the event/validator that triggered the class (e.g. `"SupervisorEvent.classified_as=Blocked"`, `"validator title.nonempty failed"`, `"ActEvent outcome=error"`). `failure_detail` is `None` only for the `"other"` and `"no_done_emitted"` classes where no specific event drives the detail.

The function is pure — it does not access `TraceWriter`, the file system, or any I/O. It is tested exclusively via synthetic event lists.

#### Scenario: status=succeeded returns (None, None)

- **WHEN** `_classify_failure(events=[], validators=[], status="succeeded")` is called
- **THEN** the result SHALL equal `(None, None)`

#### Scenario: status=skipped returns (None, None)

- **WHEN** `_classify_failure(events=[], validators=[], status="skipped")` is called
- **THEN** the result SHALL equal `(None, None)`

#### Scenario: status=unverified returns (None, None)

- **WHEN** `_classify_failure(events=[], validators=[], status="unverified")` is called
- **THEN** the result SHALL equal `(None, None)`

#### Scenario: supervisor_halt classified when SupervisorEvent policy=halt present

- **GIVEN** `events` contains a `SupervisorEvent(policy="halt", classified_as="Blocked")`
- **WHEN** `_classify_failure(events, validators=[], status="failed")` is called
- **THEN** the first element of the result SHALL equal `"supervisor_halt"`
- **AND** the second element SHALL contain `"Blocked"` (the `classified_as` value)

#### Scenario: locator_miss classified when all tiers exhausted

- **GIVEN** `events` contains a `SupervisorEvent(policy="next_tier")` followed by a `LocateEvent(outcome="miss")` with the same `step_id`
- **AND** no subsequent `LocateEvent(outcome="hit")` exists for that `step_id`
- **WHEN** `_classify_failure(events, validators=[], status="failed")` is called
- **THEN** the first element of the result SHALL equal `"locator_miss"`

#### Scenario: tool_error classified when ActEvent outcome=error present

- **GIVEN** `events` contains an `ActEvent(outcome="error", diff={"error": "TimeoutError"})` and no `SupervisorEvent`
- **WHEN** `_classify_failure(events, validators=[], status="failed")` is called
- **THEN** the first element of the result SHALL equal `"tool_error"`
- **AND** the second element SHALL reference the error detail

#### Scenario: validator_fail classified when at least one validator is not ok

- **GIVEN** `events` contains a `DoneEvent(verifier={"ok": True})` (agent called done, schema passed)
- **AND** `validators` is `[{"name": "title.nonempty", "ok": False}]`
- **WHEN** `_classify_failure(events, validators, status="failed")` is called
- **THEN** the first element of the result SHALL equal `"validator_fail"`
- **AND** the second element SHALL contain `"title.nonempty"`

#### Scenario: schema_error classified when DoneEvent verifier.ok is False

- **GIVEN** `events` contains a `DoneEvent(verifier={"ok": False, "reasons": ["missing field: title"]})`
- **AND** `validators` is `[]`
- **WHEN** `_classify_failure(events, validators, status="failed")` is called
- **THEN** the first element of the result SHALL equal `"schema_error"`
- **AND** the second element SHALL contain `"missing field: title"`

#### Scenario: no_done_emitted classified when trace has no DoneEvent

- **GIVEN** `events` contains only `ObservationEvent` and `DecisionEvent` rows with no `DoneEvent`
- **AND** `validators` is `[]`
- **WHEN** `_classify_failure(events, validators, status="failed")` is called
- **THEN** the first element of the result SHALL equal `"no_done_emitted"`

#### Scenario: other is catch-all for unrecognized failed state

- **GIVEN** `events` is `[]` and `validators` is `[]`
- **WHEN** `_classify_failure(events, validators, status="failed")` is called
- **THEN** the first element of the result SHALL equal `"other"`

#### Scenario: supervisor_halt takes priority over tool_error when both signals present

- **GIVEN** `events` contains both a `SupervisorEvent(policy="halt")` and an `ActEvent(outcome="error")`
- **WHEN** `_classify_failure(events, validators=[], status="failed")` is called
- **THEN** the first element of the result SHALL equal `"supervisor_halt"`
- **AND** NOT `"tool_error"`

### Requirement: Scoreboard surfaces failure_class column

`scripts/score.py`'s `generate_scoreboard` function SHALL include a `Failure class` column in the per-case Markdown table. For each case:

- When `failure_class` is a non-None string, the column SHALL display the literal value (e.g. `no_done_emitted`).
- When `failure_class` is `None` or the key is absent from the case dict, the column SHALL display `-`.

The summary section (pass rate, latency, token totals, mechanism firing rates) does not need to change.

#### Scenario: Failed case shows failure_class in scoreboard

- **GIVEN** a results dict with one case `{"status": "failed", "failure_class": "no_done_emitted", ...}`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the returned Markdown SHALL contain `no_done_emitted` in the per-case row

#### Scenario: Passing case shows dash in failure_class column

- **GIVEN** a results dict with one case `{"status": "succeeded", "failure_class": null, ...}`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the per-case row SHALL contain `-` in the Failure class column position

#### Scenario: Missing failure_class key shows dash (backward compat with old results)

- **GIVEN** a results dict with one case that has no `failure_class` key (old result file format)
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the per-case row SHALL display `-` without raising an error
