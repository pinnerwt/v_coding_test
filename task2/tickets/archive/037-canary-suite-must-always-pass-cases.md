---
id: 37
slug: canary-suite-must-always-pass-cases
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
filed_pr: 79
merged_pr: null
archived_at: '2026-04-29'
trigger: 'Canary suite: must-always-pass cases, hard-blocking on regression.'
---

37. **Canary suite: must-always-pass cases, hard-blocking on regression.** Carve out a `canary` category (e.g. `fixture-heading`, `fixture-count`, plus a 1-step `read URL h1`) that *must* pass on every CI run. Currently the only CI gate is "results.json exists newer than merge-base" — a no-op. Make canary regressions block merge; non-canary regressions are advisory. Tests: a fixture canary results.json with one canary failed makes the gate fail; with all canaries passing but non-canaries failed, the gate passes with a warning.
