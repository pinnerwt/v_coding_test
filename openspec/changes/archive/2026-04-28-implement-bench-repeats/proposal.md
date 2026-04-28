## Why

`scripts.benchmark` currently runs each case exactly once, making it impossible to distinguish genuinely failing cases from flaky ones. Without multi-run aggregation, a single transient LLM response fluctuation silently masquerades as a real failure; adding `--repeats N` makes flakiness visible as a fractional pass rate (e.g. `2/3`) and gives the planned canary suite (#37) a meaningful statistical foundation.

## What Changes

- **New `--repeats N` flag** on `scripts.benchmark` (default `1`; CI yaml sets `3`). When `N > 1`, each case is executed N times sequentially and results are aggregated into a single per-case summary row.
- **Per-case aggregation**: pass rate `M/N` (as `passed_runs / repeats`), median latency (ms), p95 latency (ms), stddev USD, and average `mechanism_firings` count across all N runs.
- **New `AggregatedCaseResult` dataclass** (or augmented `CaseResult`) holding repeat-run summary fields: `repeats`, `passed_runs`, `median_latency_ms`, `p95_latency_ms`, `stddev_usd`, `avg_mechanism_firings`.
- **Updated results.json shape**: when `repeats > 1`, each case entry carries the aggregated fields above instead of raw single-run fields.
- **Scoreboard row format change**: when `N > 1` the `Status` column renders `2/3 ✓` (pass-rate + check) or `1/3 ✗` (pass-rate + cross) instead of a binary `succeeded`/`failed` string. When `N == 1` the existing binary rendering is preserved.
- **Two new tests**: deterministic-mock test (3/3 with always-pass stub), flaky-stub test (fractional rate with random pass/fail stub).

## Capabilities

### New Capabilities

- `bench-repeats`: CLI flag `--repeats N` on `scripts.benchmark`, per-case repeat loop, `AggregatedCaseResult` dataclass with closed-set `RepeatStatus` field, updated results.json schema for aggregated runs, and the two TDD test shapes specified by ticket #35.

### Modified Capabilities

- `score-script`: The per-case table `Status` column rendering changes when the results JSON carries `repeats > 1` — it renders `M/N ✓` or `M/N ✗` instead of a plain status string. No other scoreboard sections change.

## Impact

- `task2/scripts/benchmark.py`: gains `--repeats N` argument and repeat-loop logic above `run_suite`.
- `task2/scripts/score.py`: `generate_scoreboard` reads an optional `repeats`/`passed_runs` from each case dict; falls back to existing binary rendering when absent (backward-compatible).
- `task2/scripts/eval.py`: `run_suite` and `_run_case` are called N times per case from benchmark.py — no changes to eval.py itself are required; the repeat loop is owned by benchmark.py.
- New test file `task2/tests/test_bench_repeats.py`.
- No dependency additions required (stdlib `statistics` module is sufficient for stddev/median).
