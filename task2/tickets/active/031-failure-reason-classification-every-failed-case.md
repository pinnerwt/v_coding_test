---
id: 31
slug: failure-reason-classification-every-failed-case
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
related: []
filed_pr: null
merged_pr: null
archived_at: null
trigger: 'migrated from task2/plan.md on 2026-04-29 (ticket #76)'
---

31. **Failure-reason classification on every failed case.** Right now `CaseResult.status="failed"` carries almost no signal — empty validators, low step count, no narrative. Add `failure_class: Literal["budget_exceeded", "tool_error", "locator_miss", "supervisor_halt", "validator_fail", "schema_error", "no_done_emitted", "other"]` and `failure_detail: str | None` to `CaseResult`, derived by `_classify_failure(events, validators, status)` from the trace (e.g. last `SupervisorEvent.classified_as`, presence of unhandled `ToolError`, validator names that failed). Surface as a column in the scoreboard. Tests: synthetic traces for each `failure_class` produce the expected classification; a passing case yields `failure_class=None`. *Why this is highest impact:* every other improvement here is bottlenecked on knowing **why** the current 6 failures fail.
