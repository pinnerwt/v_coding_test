## Why

`generate_scoreboard` in `scripts/score.py` rolls up per-case USD and latency with mixed conventions when `--repeats > 1`. `AggregatedCaseResult.usd` is the *mean* across N runs while `latency_ms_total` is the *sum* across N runs. This mismatch causes the "Total USD" line in the scoreboard to under-report actual cost by a factor of ~N when repeats > 1. Latency percentiles (p50/p95) are computed over `latency_ms_total` — which is the sum of N per-run latencies — rather than per-run values, making cross-run latency comparisons misleading. The canary suite (#37) and auto-diff vs master (#36) depend on these rollup numbers being comparable across `--repeats N` and `--repeats 1` runs.

## What Changes

- **`AggregatedCaseResult.usd` convention flipped to SUM**: align with `prompt_tokens`, `completion_tokens`, and `latency_ms_total`, all of which are already summed across N runs. The `usd` field will now be the total cost across all N runs for that case.
- **Latency percentiles computed over `median_latency_ms`** instead of `latency_ms_total`: `median_latency_ms` is the per-case median of individual run latencies, making p50/p95 across cases a meaningful per-run distribution rather than a distribution of per-case latency-sums.
- **`generate_scoreboard` `total_usd` rollup remains a simple sum** over all cases' `usd` field — once `usd` is a sum-convention field, `total_usd = sum(case.usd ...)` is correct again.
- **Two new failing tests** that pin the corrected behavior before the production change.

## Capabilities

### Modified Capabilities

- `score-script`: The latency percentile computation changes from `latency_ms_total` to `median_latency_ms` (when the field is present). The `AggregatedCaseResult.usd` semantics change (mean → sum), which keeps `total_usd` correct. Scoreboard output for `--repeats 1` runs is unchanged.

### New Capabilities

None.

## Impact

- `task2/scripts/benchmark.py`: `aggregate_repeats` must compute `usd` as sum (not mean) across N runs.
- `task2/scripts/score.py`: `generate_scoreboard` latency percentile line reads `median_latency_ms` when present (falling back to `latency_ms_total` for old results files without that field), keeping backward compatibility.
- `task2/tests/test_bench_repeats.py`: adds two new test cases covering the corrected `usd` sum and `median_latency_ms`-based percentile rollup.
- `openspec/specs/bench-repeats/spec.md`: `usd` field description updated from mean to sum.
- `openspec/specs/score-script/spec.md`: latency percentile requirement updated to reference `median_latency_ms` with fallback.
