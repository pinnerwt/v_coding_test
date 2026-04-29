---
id: 35
slug: n-run-statistical-bench-mode
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
- 37
filed_pr: null
merged_pr: null
archived_at: null
trigger: 'migrated from task2/plan.md on 2026-04-29 (ticket #76)'
---

35. **N-run statistical bench mode.** `scripts.benchmark` currently runs each case once. Add `--repeats N` (default 1, CI uses 3) that runs each case N times and reports per-case pass rate (e.g. `2/3`), median latency, p95 latency, and stddev USD. Aggregate `mechanism_firings` per case as an average. The scoreboard's per-case row shows `2/3 ✓` instead of a binary pass/fail when N>1. Tests: with `--repeats 3` and a deterministic mocked LLM client a passing case shows 3/3; injecting a flaky stub (random pass/fail) produces a fractional rate. *Why useful:* makes flakes visible and gives the canary suite (#37) a real meaning.
