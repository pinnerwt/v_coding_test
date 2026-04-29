---
id: 55
slug: urgent-investigate-benchmark-score-degradation-across
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
- task2/benchmark/*/results.json
- task2/benchmark/<branch>/results.json
related:
- 36
filed_pr: null
merged_pr: null
archived_at: null
trigger: user-flagged urgent on 2026-04-28 — performance on the benchmark degrades
  over commits and we don't yet know why.
---

55. **URGENT: Investigate benchmark-score degradation across recent commits.** Across the most recent N branches captured under `task2/benchmark/*/results.json`, the scoreboard's pass-rate, total USD, p50, and p95 trend SVGs (`task2/benchmark/_trends/*.svg`, refreshed by `scripts/trends.py`) appear to drift in the wrong direction — pass-rate trending down and/or cost+latency trending up — without a corresponding ticket explaining why. Possible drivers: (a) a stricter validator landed in some recent ticket that legitimately re-classified previously-`unverified` cases as `failed`; (b) a prompt or tool-grammar change made the agent less effective at the same cases; (c) the Qwen 27B endpoint at `localhost:8090` is itself drifting (model swap, sampling-temp change, hosting-side regression) and the benchmark is faithfully recording it; (d) a cache-warmup or fixture-state regression making one early step in each case fail more often; (e) `_render_case_status` repeats math interacts badly with `--repeats > 1` on stochastic cases (false negatives when 1/3 fail). Concrete steps: (1) read the last ~10 `task2/benchmark/<branch>/results.json` files in order of `run_at`, build a per-case time-series of `status`, `usd`, `latency_ms_total`, `step_breakdown`; (2) compute a "regression-onset" SHA per case (the first run where the case flipped passing→failing and stayed there); (3) `git log` between consecutive regression-onset SHAs to identify the candidate cause commits; (4) reproduce the worst-offending case at the suspect commit and at master to confirm the regression is in our code, not in Qwen / fixture drift. Tests: extend `task2/tests/test_trends.py` with a deterministic test that, given a synthetic 3-run series with monotonically degrading pass-rate, asserts `scripts/trends.py` flags the regression in `<!-- TRENDS:BEGIN -->` block (e.g. emits a `⚠️` next to the latest-run row when latest pass-rate is below the running median by more than X). Output artifact: a new `task2/benchmark/_trends/regression_onset.md` file enumerating each case's first-failing-SHA so future iterations can `git bisect` quickly. *Why useful:* the whole point of recording per-branch benchmarks (#36 just landed) is to detect regressions; without an active investigation when the trend visibly drifts, the trend SVGs become noise instead of signal. *Trigger:* user-flagged urgent on 2026-04-28 — performance on the benchmark degrades over commits and we don't yet know why.
