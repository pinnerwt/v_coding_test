---
id: 40
slug: cost-latency-budget-overruns-soft-failures
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
trigger: ''
---

40. **Cost & latency budget overruns as soft failures.** Right now `budget` in YAML is enforced (case fails if exceeded) but a case using 95% of its step budget shows up identical to one using 5%. Add a `near_budget: bool` flag (true if any of `steps / usd / seconds` is ≥80% of its limit) on passing cases. Surface as a "⚠️" annotation in the scoreboard. Tests: a synthetic run at 80% step budget with status `succeeded` produces `near_budget=True`; at 79% produces `False`. *Why useful:* early warning before regressions push a case over the cliff.
