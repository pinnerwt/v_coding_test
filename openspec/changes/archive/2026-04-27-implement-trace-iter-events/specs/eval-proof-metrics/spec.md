## MODIFIED Requirements

### Requirement: _aggregate_diagnostics reads trace rows into CaseResult diagnostic fields

The system SHALL provide a module-level function `_aggregate_diagnostics(writer: TraceWriter, run_id: str) -> tuple[list[dict], int, dict]` in `scripts/eval.py` that:

1. Obtains all events for `run_id` by calling `writer.iter_events(run_id)` and materialising the result into a list — it SHALL NOT call `writer._require_conn().execute(...)` directly.
2. Deserialisation is performed by `TraceWriter.iter_events`; `_aggregate_diagnostics` SHALL NOT import or call `_any_event_adapter` from `agent.trace`.
3. Collects each `SupervisorEvent` with `policy="next_tier"` and builds an escalation dict: `from_tier` is the `tier` of the `LocateEvent` whose `seq` matches `trigger_event_seq` (looked up from the `locates_by_seq` index); `to_tier` is the `tier` of the first `LocateEvent` after this `SupervisorEvent` in sequence with `outcome="hit"` and the same `step_id` (or `None` if none exists in the trace); `intent` is the `intent` field of the triggering `LocateEvent`; `reason` is the supervisor event's `classified_as` field lowercased.
4. Counts `PlanEvent` rows with `reason="replan"`.
5. Counts `LocateEvent` rows by `cache_action`: `cache_action="read"` with `outcome="hit"` → `hits`; `cache_action="invalidate"` → `invalidations`; `outcome="miss"` with `cache_action` is `None` → `misses`.
6. Returns `(escalations_list, replan_count, cache_events_dict)`.

`_aggregate_diagnostics` SHALL be callable with an in-memory `TraceWriter` that has been used during a `loop()` call.

The import `from agent.trace import _any_event_adapter` SHALL NOT appear anywhere in `scripts/eval.py`.

#### Scenario: Aggregates escalation from SupervisorEvent sequence

- **GIVEN** a `TraceWriter` whose trace contains (in seq order): a `LocateEvent(tier="L1_ax", outcome="miss", cache_action=None)` then a `SupervisorEvent(policy="next_tier", classified_as="LocatorMiss")` then a `LocateEvent(tier="L2_dom", outcome="hit", cache_action="write")`
- **WHEN** `_aggregate_diagnostics(writer, run_id)` is called
- **THEN** the returned escalations list SHALL contain exactly one entry
- **AND** that entry SHALL have `from_tier="L1_ax"` and `to_tier="L2_dom"`

#### Scenario: Counts replans from PlanEvent rows

- **GIVEN** a `TraceWriter` whose trace contains one `PlanEvent(reason="initial")` and one `PlanEvent(reason="replan")`
- **WHEN** `_aggregate_diagnostics(writer, run_id)` is called
- **THEN** the returned replan count SHALL equal `1`

#### Scenario: Counts cache events from LocateEvent rows

- **GIVEN** a `TraceWriter` whose trace contains: one `LocateEvent(cache_action="read", outcome="hit")`, one `LocateEvent(cache_action="invalidate", outcome="miss")`, one `LocateEvent(cache_action=None, outcome="miss")`
- **WHEN** `_aggregate_diagnostics(writer, run_id)` is called
- **THEN** `cache_events["hits"]` SHALL equal `1`, `cache_events["invalidations"]` SHALL equal `1`, `cache_events["misses"]` SHALL equal `1`

#### Scenario: Empty trace returns zero values

- **GIVEN** a `TraceWriter` with an open run but no events
- **WHEN** `_aggregate_diagnostics(writer, run_id)` is called
- **THEN** the returned escalations SHALL be `[]`, replan count SHALL be `0`, cache_events SHALL equal `{"hits": 0, "invalidations": 0, "misses": 0}`

#### Scenario: _aggregate_diagnostics does not import _any_event_adapter from agent.trace

- **WHEN** `scripts/eval.py` is inspected for import statements
- **THEN** `from agent.trace import _any_event_adapter` SHALL NOT appear in the file
