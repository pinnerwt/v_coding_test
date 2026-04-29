---
id: 26
slug: tracewriter-next-seq-run-id-accessor
status: active
tier: 6
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related:
- 20
filed_pr: null
merged_pr: null
archived_at: null
trigger: 'migrated from task2/plan.md on 2026-04-29 (ticket #76)'
---

26. **`TraceWriter.next_seq(run_id)` accessor; eliminate per-event-kind seq counters in `loop.py`** — `loop.py` currently maintains a local `plan_seq` counter that increments before each `_emit_plan_event` call and is passed in as the `seq` for the constructed `PlanEvent`. This works today only because `loop()` is the sole writer of events for a given `run_id` in `api/server.py::_run_agent`. As soon as a second emitter (e.g. `ObservationEvent` / `DecisionEvent` / `LLMCallEvent` wiring per ticket #20, or any future caller writing events for the same run from outside `loop()`) starts using the same `TraceWriter` in the same run, the local `plan_seq` will collide with `TraceWriter`'s authoritative `MAX(seq)` check and raise `SeqError`. Add a public method `TraceWriter.next_seq(run_id) -> int` that returns `MAX(seq) + 1` for the run (or 1 if no events yet), and refactor `_emit_plan_event` (and any future event-emit helpers in `loop.py`) to call `next_seq()` instead of carrying a local counter. Tests: `next_seq` on a freshly-opened run returns 1; after appending an event with seq=N, returns N+1; two interleaved emitters writing to the same run produce strictly-increasing seq with no `SeqError` (concretely: emit a `PlanEvent` via `loop()`, then emit a manually-constructed `ObservationEvent` from the test using `next_seq()`, and verify both land); the existing `plan_seq` counter in `loop.py` is removed.
