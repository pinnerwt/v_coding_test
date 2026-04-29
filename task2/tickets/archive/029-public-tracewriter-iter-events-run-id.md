---
id: 29
slug: public-tracewriter-iter-events-run-id
status: archived
tier: 4
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related: []
filed_pr: null
merged_pr: null
archived_at: '2026-04-28'
trigger: Public `TraceWriter.iter_events(run_id)` and stop reaching into private trace
  internals from `scripts/eval.py`
---

29. **Public `TraceWriter.iter_events(run_id)` and stop reaching into private trace internals from `scripts/eval.py`** — `_aggregate_diagnostics` currently calls `writer._require_conn().execute(...)` and imports the private `_any_event_adapter` from `agent.trace` to deserialize trace rows. That couples the eval runner to `TraceWriter` implementation details and breaks if the storage backend, the schema, or the adapter symbol is renamed. Add a public `TraceWriter.iter_events(run_id) -> Iterator[AnyEvent]` method on `agent.trace.TraceWriter` that yields parsed events in `seq` order for the given run, and refactor `_aggregate_diagnostics` to consume it instead of issuing raw SQL and parsing payloads itself. Tests: `iter_events` on a writer with no events for the run returns an empty iterator; on a writer with N appended events returns them in `seq` order with the same Pydantic types `_any_event_adapter.validate_json` produces today; switching `_aggregate_diagnostics` over leaves all existing diagnostic-aggregation tests green; `from agent.trace import _any_event_adapter` no longer appears in `scripts/eval.py`.
