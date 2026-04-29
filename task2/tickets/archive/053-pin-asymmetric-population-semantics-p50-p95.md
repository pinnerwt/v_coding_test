---
id: 53
slug: pin-asymmetric-population-semantics-p50-p95
status: archived
tier: 2
urgency: P2
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related:
- 76
filed_pr: 118
merged_pr: 118
archived_at: '2026-04-29'
trigger: 'surfaced by review subagent on PR #76 (iteration 1).'
---

53. **Pin asymmetric-population semantics for `Δ p50` / `Δ p95` latency in `baseline_diff.py`.** `task2/scripts/baseline_diff.py::generate_diff_markdown` computes the latency percentile delta over the *entire* per-case populations of master vs branch, regardless of whether the case sets match (`m_lat = [c.latency_ms_total for c in master_cases]` vs same for branch). When branch adds a new case or drops one, the populations differ in size, and the resulting `Δ p50 latency` can flip sign for reasons unrelated to per-case regression (population-shift artifact, not real change). Decision needed: (a) restrict the latency aggregation to the intersection of case ids (`set(master_ids) & set(branch_ids)`) so the delta reflects only common-case drift, (b) keep whole-population semantics and document the caveat in `diff.md` ("aggregate latency includes new/dropped cases"), or (c) emit both numbers (intersection p50/p95 + whole-population p50/p95). Tests: a synthetic master + branch where branch adds one fast case (`+1 case at 100ms`) but all common cases are unchanged — assert the chosen-semantic delta is what the spec says (e.g. `Δ p50 latency: +0ms` under intersection semantics). *Why useful:* the auto-diff feature's whole point is to surface real regressions; population-shift artifacts undermine reviewer trust. *Trigger:* surfaced by review subagent on PR #76 (iteration 1).
