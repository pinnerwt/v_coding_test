---
id: 38
slug: per-step-token-latency-breakdown-surfacing
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
filed_pr: 81
merged_pr: null
archived_at: null
trigger: 'migrated from task2/plan.md on 2026-04-29 (ticket #76)'
---

38. **Per-step token / latency breakdown surfacing.** `CaseResult.step_breakdown` already exists per ticket #20, but the scoreboard only shows totals. Add a `--detail` flag (or always-on in markdown but collapsed in `<details>`) that emits a per-step table for each failing case: step index, tool called, observation token count, decision token count, latency. *Why useful:* a step that uses 10× the average tokens is a leak (e.g. AX-tree observation balloons), a step >30s on a fast page is a Playwright stall — both invisible in current totals.
