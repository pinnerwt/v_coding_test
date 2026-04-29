---
id: 36
slug: auto-diff-scoreboard-against-master-baseline
status: active
tier: 2
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence:
- task2/benchmark/master/results.json
related: []
filed_pr: 76
merged_pr: null
archived_at: null
trigger: ''
---

36. **Auto-diff scoreboard against master baseline.** When `--branch` is non-master, also load `task2/benchmark/master/results.json` and emit a "Δ vs master" table: per-case status delta (newly-passing / newly-failing / unchanged), aggregate pass-rate delta, total USD delta, p50/p95 latency delta. Wire `task2-benchmark` CI workflow to post the diff as a PR comment. Tests: synthetic master + branch results.json pairs produce the expected diff markdown; a no-op branch (identical to master) produces an empty Δ table; a previously-passing case now failing is flagged as a regression with severity.
