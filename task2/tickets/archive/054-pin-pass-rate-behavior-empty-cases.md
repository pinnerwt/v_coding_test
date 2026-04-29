---
id: 54
slug: pin-pass-rate-behavior-empty-cases
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
filed_pr: 132
merged_pr: 132
archived_at: '2026-04-29'
trigger: 'surfaced by review subagent on PR #76 (iteration 1).'
---

54. **Pin `Δ pass-rate` behavior for empty-cases / all-skipped runs in `baseline_diff.py`.** `task2/scripts/baseline_diff.py::generate_diff_markdown` computes `m_pct = int(100 * _pass_count(m_list) / m_ran) if m_ran else 0` and `b_pct` likewise; when either run has zero cases or all-skipped cases (`m_ran == 0`), it silently emits `Δ pass-rate: +0%` rather than `n/a`. Likewise `Δ total USD` and `Δ p50/p95 latency` over an all-skipped branch will report `+$0.0000` and `+0ms`, which a reviewer would read as "no regression" when the truth is "no signal". Decision needed: (a) emit `Δ pass-rate: n/a (master had 0 ran cases)` (and similarly for USD/latency) when a side has no runnable cases, (b) keep `+0%` and add a one-line note above the aggregate block when applicable, or (c) suppress the aggregate block entirely. Tests: synthetic `master_results.json` with `cases: []` paired with non-empty branch — assert the chosen output makes the empty-side state visible. *Why useful:* prevents the auto-diff from silently misclassifying "no data" as "no regression", a high-confusion failure mode at PR-review time. *Trigger:* surfaced by review subagent on PR #76 (iteration 1).
