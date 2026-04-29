## 1. Failing Tests — total_usd under repeats=3 (Red phase)

- [x] 1.1 In `task2/tests/test_bench_repeats.py`, add a test `test_scoreboard_total_usd_with_repeats`: construct a synthetic `data` dict with two non-skipped cases each having `usd=0.03` (sum of three runs at $0.01 each) and `repeats=3`; call `aggregate_repeats` to get the aggregated result and assert `result.usd == 0.03` (confirming the sum convention is preserved per-case).
- [x] 1.2 Concretely: use two cases with `usd=0.01` (current mean convention) and `repeats=3`; assert `generate_scoreboard` output contains `Total USD: $0.0600` (i.e. `0.01 × 3 runs × 2 cases = $0.06`). With the current code the test will fail because it reports `$0.0200`.
- [x] 1.3 Run `uv run pytest task2/tests/test_bench_repeats.py::test_scoreboard_total_usd_with_repeats -x` from `task2/` and confirm it fails with an `AssertionError` (output shows `$0.0200` not `$0.0600`).

## 2. Failing Tests — latency p50/p95 over per-run scalars (Red phase)

- [x] 2.1 In `task2/tests/test_bench_repeats.py`, add a test `test_scoreboard_latency_percentiles_with_repeats`: construct a synthetic `data` dict with three non-skipped cases having `median_latency_ms` values `[100, 200, 800]` and `latency_ms_total` values `[300, 600, 2400]` (sum of 3 runs each); call `generate_scoreboard(data)` and assert `p50: 200ms` and `p95: 800ms` appear in the output — confirm it fails because the current code uses `latency_ms_total` and would report `p50: 600ms  p95: 2400ms`.
- [x] 2.2 Run `uv run pytest task2/tests/test_bench_repeats.py::test_scoreboard_latency_percentiles_with_repeats -x` from `task2/` and confirm it fails with an `AssertionError`.

## 3. Production change — `AggregatedCaseResult.usd` → SUM convention

- [x] 3.1 In `task2/scripts/benchmark.py`, locate `aggregate_repeats` and change the `usd` field computation from mean (`statistics.mean(usd_vals)` or equivalent) to sum (`sum(usd_vals)`). Update the inline comment if one exists.
- [x] 3.2 Run `uv run pytest task2/tests/test_bench_repeats.py::test_scoreboard_total_usd_with_repeats -x` and confirm it now passes.
- [x] 3.3 Run `uv run pytest task2/tests/test_bench_repeats.py -x` and confirm no regressions in the existing bench-repeats tests (the `usd` field semantics change should not break tests that only check `passed_runs`, `repeats`, `repeat_status`, or `median_latency_ms`).

## 4. Production change — latency percentile input in `generate_scoreboard`

- [x] 4.1 In `task2/scripts/score.py`, locate the latency percentile block (approximately line 221):
  ```python
  latencies = [c.get("latency_ms_total", 0) for c in non_skipped]
  ```
  Replace with:
  ```python
  latencies = [
      c.get("median_latency_ms", c.get("latency_ms_total", 0))
      for c in non_skipped
  ]
  ```
- [x] 4.2 Run `uv run pytest task2/tests/test_bench_repeats.py::test_scoreboard_latency_percentiles_with_repeats -x` and confirm it now passes.
- [x] 4.3 Run `uv run pytest task2/tests/test_score.py -x` and confirm the existing latency percentile tests still pass (`test_score_percentile_*`, etc.).

## 5. Backward compatibility — single-run results unaffected

- [x] 5.1 Verify that existing single-run scenario test `test_score_has_total_usd_and_tokens` (or equivalent in `test_score.py`) still passes — the `median_latency_ms` fallback must not break old results files.
- [x] 5.2 If the golden snapshot `tests/fixtures/results/sample_results_scoreboard.md` encodes stale values from the pre-fix code, regenerate it by running `uv run python scripts/score.py tests/fixtures/results/sample_results.json > tests/fixtures/results/sample_results_scoreboard.md` (only if the snapshot test fails after the fix — do not regenerate proactively).

## 6. Ruff and full pytest pass

- [x] 6.1 Run `uv run ruff check task2/scripts/benchmark.py task2/scripts/score.py task2/tests/test_bench_repeats.py` and fix any lint errors.
- [x] 6.2 Run `uv run ruff format task2/scripts/benchmark.py task2/scripts/score.py task2/tests/test_bench_repeats.py`.
- [x] 6.3 Run `uv run pytest task2/tests/ -v` from `task2/` and confirm the full suite is green.
