---
id: 25
slug: planevent-integration-tracewriter-loop-py
status: archived
tier: 5
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
archived_at: '2026-04-29'
trigger: '`PlanEvent` integration with `TraceWriter` in `loop.py`'
---

25. **`PlanEvent` integration with `TraceWriter` in `loop.py`** — `_emit_plan_event` in `loop.py` emits `PlanEvent` instances into an in-memory `events: list | None` parameter using placeholder values (`run_id="loop"`, `seq=0`, `ts=""`) so existing test fixtures can assert event ordering. Real runs that persist traces via `TraceWriter` (used elsewhere for `ObservationEvent`/`DecisionEvent`/`LLMCallEvent`) will not capture plan events with valid metadata. Wire the loop to a `TraceWriter` (or equivalent emitter) so `PlanEvent` rows land in the JSONL alongside other events with the run's actual `run_id`, monotonic `seq`, and ISO `ts`. Tests: a real loop run with a `TraceWriter` produces a JSONL file containing `kind="plan"` rows with non-placeholder `run_id`, strictly increasing `seq` (interleaved correctly with surrounding events), and ISO-formatted `ts`; the in-memory `events` list test path keeps working (back-compat); `_emit_plan_event`'s `reason` parameter is typed `Literal["initial", "replan"]` so the existing `# type: ignore[arg-type]` is removed.
