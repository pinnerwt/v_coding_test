## Context

`AggregatedCaseResult` in `scripts/benchmark.py` stores per-case aggregated statistics from N runs. The fields `prompt_tokens`, `completion_tokens`, and `latency_ms_total` are all SUM conventions (total across N runs). The `usd` field was specified as the *mean* — the only aggregated numeric field using a mean rather than sum convention. The scoreboard rolls up with `total_usd = sum(case.usd ...)` over all cases; with a mean convention this produces total_usd ≈ true_cost / N.

`generate_scoreboard` computes latency percentiles as `_percentile([c.latency_ms_total for c ...], P)`. When `latency_ms_total` is the sum across N runs, the distribution being percentiled is a distribution of per-case *total* latencies — not per-run latencies. A case with 3 runs × 300ms each has `latency_ms_total=900`, while a single-run case at 900ms also has `latency_ms_total=900`. The `median_latency_ms` field (the actual median of the N per-run latencies) already exists on `AggregatedCaseResult` and is the correct input for cross-case percentile comparison.

## Decision: Option (a) — flip `usd` to SUM convention

**Choice**: flip `AggregatedCaseResult.usd` to the sum (total) convention, matching `prompt_tokens`, `completion_tokens`, and `latency_ms_total`.

**Rationale**: All three sibling numeric fields already use sum convention. Aligning `usd` eliminates the convention mismatch and makes `generate_scoreboard`'s `total_usd = sum(case.usd ...)` correct with zero changes to the rollup logic. Option (b) — multiplying `usd × repeats` at scoreboard rollup time — would fix the total but leave the per-case `usd` cell displaying a single-run mean, which is confusing next to per-case prompt_tokens/latency_ms_total that represent totals. Option (c) — aggregation-aware accessors — adds indirection without changing the underlying representation inconsistency.

**Trade-offs**: Any consumer reading `AggregatedCaseResult.usd` as a mean (e.g. "cost per run") will need to divide by `repeats`. There are no such callers in the current codebase; `usd` is read only by the scoreboard rollup (`total_usd += usd`) and the per-case cell (`$usd:.4f`). The per-case cell will now show total cost for that case across N runs, which is what a reviewer comparing multi-run vs single-run scoreboard rows wants to see.

## Latency percentile fix

The `_percentile` call in `generate_scoreboard` SHALL be changed to:

```python
latencies = [
    c.get("median_latency_ms", c.get("latency_ms_total", 0))
    for c in non_skipped
]
```

This reads `median_latency_ms` when present (the per-case per-run median, set by `aggregate_repeats`) and falls back to `latency_ms_total` for old results files or `--repeats 1` runs (where the two fields are identical in meaning). This keeps the scoreboard backward-compatible with existing fixture files that have no `median_latency_ms` key.

## Goals / Non-Goals

**Goals:**
- Correct `AggregatedCaseResult.usd` from mean to sum convention.
- Correct `generate_scoreboard` latency percentile input to use `median_latency_ms` with fallback.
- Add two failing tests that pin the corrected behavior before touching production code.
- Keep backward compatibility: `--repeats 1` runs and old results files are unaffected.

**Non-Goals:**
- Changing the per-case Latency (ms) column in the scoreboard table (it still shows `latency_ms_total`).
- Aggregating `escalations` or `cache_events` across runs.
- Any change to `eval.py`, `benchmark.py`'s `--repeats` CLI, or the drift/canary suite config.

## Risks / Trade-offs

- [Risk] Existing golden snapshot fixture `sample_results_scoreboard.md` encodes the current (broken) `total_usd` value. The golden snapshot will need to be regenerated after the fix. This is expected and is part of the green phase.
- [Risk] Per-case `usd` cell in the scoreboard now shows total-run cost rather than per-run cost. Adding a note or changing the column header is out of scope here; it can be a follow-up cosmetic ticket.
