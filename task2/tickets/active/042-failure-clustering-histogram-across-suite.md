---
id: 42
slug: failure-clustering-histogram-across-suite
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
- 31
filed_pr: 83
merged_pr: null
archived_at: null
trigger: 'migrated from task2/plan.md on 2026-04-29 (ticket #76)'
---

42. **Failure-clustering histogram across the suite.** Once #31 lands, aggregate `failure_class` counts across all failed cases and emit a histogram block at the top of the scoreboard (e.g. "5× supervisor_halt, 1× locator_miss"). Trend the per-class counts in `_trends/` as a stacked area chart, similar to the existing pass-rate / latency / cost trends. Tests: synthetic results.json with mixed `failure_class` values produces the expected histogram and trend SVG.
