---
id: 51
slug: aggregation-aware-scoreboard-rollups-when-repeats
status: active
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
- 37
- 36
- 75
filed_pr: null
merged_pr: null
archived_at: null
trigger: 'surfaced by review subagent on PR #75 (iteration 3).'
---

51. **Aggregation-aware scoreboard rollups when `--repeats > 1`.** `task2/scripts/score.py::generate_scoreboard` rolls up per-case fields with simple sums: `total_usd = sum(case.usd ...)`, `p50 / p95 = _percentile([case.latency_ms_total for case ...], P)`. With `--repeats > 1` the per-case `usd` is the mean across N runs (per current spec) while `latency_ms_total` is the sum across N runs — so the "Total USD" line under-reports actual cost by ~1/N, and the latency percentile is computed over per-case-summed values rather than per-run values. Decision needed: (a) flip `AggregatedCaseResult.usd` to the SUM convention (matching `prompt_tokens` / `completion_tokens` / `latency_ms_total`) and update the spec, (b) make `score.py` multiply `usd × repeats` when rolling up, or (c) add explicit aggregation-aware accessors. Tests: a 3-repeat synthetic scoreboard with known per-run usd correctly reports total cost; the same with known per-run latencies reports a meaningful p50/p95 (most naturally over `median_latency_ms`). *Why useful:* the canary suite (#37) and the auto-diff vs master (#36) both depend on these rollup numbers being comparable across `--repeats N` and `--repeats 1` runs. *Trigger:* surfaced by review subagent on PR #75 (iteration 3).
