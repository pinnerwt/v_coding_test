---
id: 78
slug: propagate-aggregated-usd-sum-convention-across-consumers
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
- 51
- 36
- 37
filed_pr: null
merged_pr: null
archived_at: null
trigger: 'surfaced by review subagent on PR #111 (iteration 3) — flagged that the convention flip in #51 did not propagate to all consumers of `usd` and `latency_ms_total`.'
---

78. **Propagate the `AggregatedCaseResult.usd` SUM convention and the `median_latency_ms` percentile preference to every consumer of bench results.** Ticket #51 (PR #111) flipped `AggregatedCaseResult.usd` from MEAN-across-N-runs to SUM, and switched `score.py::generate_scoreboard`'s percentile input from `latency_ms_total` to `median_latency_ms` with `latency_ms_total` fallback. Two adjacent consumers were not updated, and one new edge case is unguarded. Concrete deliverables: (1) `task2/scripts/baseline_diff.py` aggregates `c.get("usd", 0.0)` and `c.get("latency_ms_total", 0)` over master and branch results to produce `Δ total USD` and `Δ p50/p95 latency`; under cross-`repeats` comparison (master `--repeats 1` vs branch `--repeats 3`) the deltas are now systematically inflated. Fix: normalize each case's `usd` by `case.get("repeats", 1)` and use `median_latency_ms` (with the same fallback chain as score.py) for percentile input. Add a regression test pairing a `repeats=1` master against a `repeats=3` branch with identical underlying behavior asserting `Δ USD ≈ 0` and `Δ p50 ≈ 0`. (2) `task2/scripts/trends.py` sums `c.get("usd", 0.0)` across cases and renders per-case `${usd:.4f}` cells without dividing by `repeats`. With the convention flip, historical `--repeats N` runs on the trend SVGs and the markdown trend table will plot a step-up in `total_usd` purely from convention drift. Fix: same normalization pattern (or introduce a `usd_per_run` helper) and add a test that a multi-run results file with known per-run cost lands at the expected total. Decide whether to retroactively re-render or version-tag the existing trend artifacts so the convention boundary is visible. (3) `task2/scripts/score.py`'s per-case scoreboard table column labelled `USD` now silently means "total cost across N runs" when `repeats > 1`, while readers expect per-run cost. Either rename the column to `USD (total)` when any case has `repeats > 1`, or normalize the cell to per-run USD by dividing by `repeats` for display. Add a snapshot test that pins the chosen rendering for a `repeats=3` case. (4) Within a single results file, mixed presence of `median_latency_ms` (some cases have it, others don't) causes the percentile to mix per-run-median scalars with sum-across-N-runs scalars — meaningless. Tighten `score.py:_percentile` input: when the set of present `median_latency_ms` keys is mixed across non-skipped cases, raise or skip the percentile line with a one-line warning rather than silently mixing units. Add a test constructing a mixed-case file and asserting the chosen behavior. (5) End-to-end roundtrip test: run `aggregate_repeats` (with stubbed `_run_case`) → serialize via the same path `eval.py` uses to write `results.json` → feed to `generate_scoreboard` → assert `Total USD` matches the true sum. This pins the convention contract between writer and reader at the integration boundary, complementing the unit-level tests already in `test_bench_repeats.py`. *Why useful:* PR #111 makes `score.py`'s rollups correct for the standalone scoreboard, but #36 (auto-diff vs master) and #37 (canary suite) both consume the same results JSONs through different code paths. Without this propagation, those features will report wrong deltas the moment anyone runs `bench --repeats > 1`, undermining the very signal they exist to provide. Today the WebVoyager bench doesn't expose `--repeats` on the CLI so the bug is forward-looking, but the convention boundary should be closed before `--repeats > 1` becomes routine. *Risks:* (a) baseline_diff.py / trends.py have their own test surfaces and changing aggregation could break existing snapshot tests — mitigation is to update snapshots in lockstep; (b) the column-rename / divide-for-display decision in (3) is a UX call that needs a single-author choice, not a mechanical fix — make it in design.md before implementing. *Trigger:* surfaced by review subagent on PR #111 (iteration 3) — flagged that the convention flip in #51 did not propagate to all consumers of `usd` and `latency_ms_total`.
