---
id: 30
slug: thread-step-id-through-event-emitters
status: active
tier: 2
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
- 27
filed_pr: 58
merged_pr: null
archived_at: null
trigger: ''
---

30. **Thread `step_id` through event emitters in `loop.py`** — `_emit_plan_event` and `_emit_locate_event` in `agent/loop.py` both hardcode `step_id=None` when constructing their respective `EventBase` subclasses, even though `EventBase.step_id: str | None` exists for exactly this attribution. As a result, plan / locate trace rows cannot be joined back to the step that produced them, which weakens any per-step diagnostic the eval runner builds (e.g. "which step did the cache invalidate fire on?", "which step triggered replan?"). Define a step identifier convention (e.g. `f"{run_id}:step-{i}"` derived from the loop's existing per-step counter) and thread it from `loop()` into `_dispatch` → `_locate_with_supervisor` → `_emit_locate_event`, and from `loop()` into `_emit_plan_event`. Tests: a real loop run with a `TraceWriter` produces `PlanEvent` rows whose `step_id` matches the step index that triggered them (initial plan after step 1 → `step_id` references step 1; replan after a halt on step N → `step_id` references step N); `LocateEvent` rows emitted from cache actions on step N carry `step_id` matching that step; the existing in-memory `events` test path continues to work; `step_id` formatting is consistent with whatever `ObservationEvent` / `DecisionEvent` emit once those are wired (ticket #20).

**Done bar**: drift suite 100%, fixture eval ≥ 80%, live ≥ 60% (or honest number reported), deployed Zeabur URL reachable, prompts captured under `prompts/task2/`.


Observed state from the 2026-04-27 run on `task2/implement-trace-iter-events` (8 ran, 5 skipped):

- **2/8 pass** (25%). Only the trivially easy `fixture-heading` / `fixture-count` succeed. Drift, correction, replan, and rename cases all fail.
- **Mechanism-firing columns are 0/8 across the board.** Escalations 0, Replans 0, Cache invalidations 0 — including on the very cases (`correction-l1-miss-l2-hit`, `correction-replan`, `maintenance-drift-rename-v1/v2`) that ticket #27 introduced specifically to prove those mechanisms fire. The unit tests in `test_eval.py` pass, but the live benchmark contradicts them: somewhere between unit-test mocks and the real `loop()` + Qwen 27B, the mechanisms are not engaging.
- **Failing cases halt very early** (1-3 steps out of 5-step budgets). Validators on most failed cases are `[]`, so the only signal is "agent didn't reach `done`" — no failure-reason classification.
- **5/13 live cases skipped silently** — no skip-reason recorded, so it's not clear which are infra-skipped vs. feature-skipped.
- **Single run per branch.** Stochastic-LLM noise is invisible; one bad sample looks identical to a real regression.

Candidate tickets, ordered roughly by impact-per-effort. Each is TDD-shaped so it can drop straight into the `TDD tickets` list above when promoted.
