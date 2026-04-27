# eval-proof-metrics Specification

## Purpose
TBD - created by archiving change implement-self-correction-proof. Update Purpose after archive.

## Requirements

### Requirement: CaseResult diagnostic mechanism fields

`scripts.eval.CaseResult` SHALL gain three new diagnostic fields with zero/empty defaults for backward compatibility:

- `escalations: list[dict] = field(default_factory=list)` — one entry per `SupervisorEvent` with `policy="next_tier"` in the case trace. Each entry is a dict with keys `intent: str`, `from_tier: str`, `to_tier: str | None`, `reason: str`.
- `replans: int = 0` — count of `PlanEvent(reason="replan")` rows in the case trace.
- `cache_events: dict = field(default_factory=dict)` — aggregate counts from `LocateEvent` rows. Keys: `hits` (int), `invalidations` (int), `misses` (int). All default to 0 when no locate events are present.

Existing fields (`id`, `status`, `steps`, `usd`, `l_tier_counts`, `validators`, `prompt_tokens`, `completion_tokens`, `latency_ms_total`, `latency_ms_per_step`, `step_breakdown`) are unchanged.

#### Scenario: CaseResult is constructible without new fields (backward compat)

- **WHEN** `CaseResult(id="x", status="succeeded", steps=0, usd=0.0, l_tier_counts={}, validators=[])` is constructed
- **THEN** `escalations` SHALL equal `[]`, `replans` SHALL equal `0`, `cache_events` SHALL equal `{}`

#### Scenario: CaseResult with new fields serialises to JSON

- **GIVEN** a `CaseResult` with `escalations=[{"intent": "Submit button", "from_tier": "L1_ax", "to_tier": "L2_dom", "reason": "zero_matches"}]`, `replans=1`, `cache_events={"hits": 1, "invalidations": 1, "misses": 0}`
- **WHEN** `asdict(case_result)` is passed through `json.dumps`
- **THEN** the JSON SHALL contain `"escalations"`, `"replans"`, and `"cache_events"` keys with the correct values

### Requirement: _aggregate_diagnostics reads trace rows into CaseResult diagnostic fields

The system SHALL provide a module-level function `_aggregate_diagnostics(writer: TraceWriter, run_id: str) -> tuple[list[dict], int, dict]` in `scripts/eval.py` that:

1. Queries all event rows for `run_id` from the `TraceWriter`'s SQLite database ordered by `seq`.
2. Deserialises each event payload using the `AnyEvent` type adapter from `agent.trace`.
3. Collects each `SupervisorEvent` with `policy="next_tier"` and builds an escalation dict: `from_tier` is the `tier` of the most recent `LocateEvent` before this `SupervisorEvent` in sequence (same or earlier); `to_tier` is the `tier` of the first `LocateEvent` after this `SupervisorEvent` in sequence with `outcome="hit"` (or `None` if none exists in the trace); `intent` is the `intent` field of the triggering `LocateEvent`; `reason` is `miss.reason` derivable from the supervisor event's `classified_as` field (lowercased).
4. Counts `PlanEvent` rows with `reason="replan"`.
5. Counts `LocateEvent` rows by `cache_action`: `cache_action="read"` with `outcome="hit"` → `hits`; `cache_action="invalidate"` → `invalidations`; `outcome="miss"` with `cache_action` is `None` → `misses`.
6. Returns `(escalations_list, replan_count, cache_events_dict)`.

`_aggregate_diagnostics` SHALL be callable with an in-memory `TraceWriter` that has been used during a `loop()` call.

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

### Requirement: _run_case threads TraceWriter through loop and populates diagnostic fields

`_run_case` SHALL create an in-memory `TraceWriter` and a `uuid4()` `run_id` before calling `loop()`, pass them as `trace_writer=writer, run_id=run_id`, then call `_aggregate_diagnostics(writer, run_id)` after `loop()` returns, and populate the new `CaseResult` fields from the aggregation result.

#### Scenario: _run_case produces non-empty escalations for a case where L1 missed and L2 hit

- **GIVEN** a mocked `loop()` that emits a `SupervisorEvent(policy="next_tier")` preceded by `LocateEvent(tier="L1_ax", outcome="miss")` and followed by `LocateEvent(tier="L2_dom", outcome="hit")` in the trace writer passed to it
- **WHEN** `_run_case(case, llm_client, browser)` is called
- **THEN** the returned `CaseResult.escalations` SHALL contain exactly one entry
- **AND** that entry SHALL have `from_tier="L1_ax"` and `to_tier="L2_dom"`

#### Scenario: _run_case produces replans=1 for a case where halt triggered replan

- **GIVEN** a mocked `loop()` that emits a `PlanEvent(reason="replan")` to the trace writer
- **WHEN** `_run_case(case, llm_client, browser)` is called
- **THEN** `CaseResult.replans` SHALL equal `1`
