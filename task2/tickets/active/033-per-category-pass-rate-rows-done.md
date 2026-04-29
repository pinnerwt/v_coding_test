---
id: 33
slug: per-category-pass-rate-rows-done
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
filed_pr: 71
merged_pr: null
archived_at: null
trigger: 'migrated from task2/plan.md on 2026-04-29 (ticket #76)'
---

33. **Per-category pass-rate rows + done-bar traffic lights in the scoreboard.** Group cases by `category` and emit a summary table. Surface the `Done bar` thresholds explicitly: "Drift suite: 0/4 (0%) [target 100%] ❌", "Fixture: 2/2 (100%) [target 80%] ✅", "Live: 0/0 ran [target 60%] ⏭️". Keep the per-case table below it. Tests: `score.py` against a vendored fixture results.json produces the expected category aggregation; thresholds come from a config block (no hardcoded magic numbers).
