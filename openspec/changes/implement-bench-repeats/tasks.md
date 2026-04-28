## 1. Failing Tests (Red phase)

- [x] 1.1 Create `task2/tests/test_bench_repeats.py` with Test 1: write a test that calls `aggregate_repeats(case, repeats=3, ...)` with `_run_case` patched to always return `status="succeeded"` and asserts `passed_runs == 3`, `repeats == 3`, `repeat_status == "all_pass"` — confirm it fails with `ImportError` or `AttributeError`
- [x] 1.2 Add Test 2 to `test_bench_repeats.py`: write a test that patches `_run_case` with statuses `["succeeded", "failed", "failed"]` and asserts `passed_runs == 1`, `repeats == 3`, `repeat_status == "partial"` — confirm it also fails
- [x] 1.3 Add a test for `--repeats 0` rejection: assert that `benchmark.main(["--repeats", "0"])` exits non-zero — confirm it fails
- [x] 1.4 Add a test for `AggregatedCaseResult` rejects unknown `repeat_status` (`ValueError` on construction) — confirm it fails
- [x] 1.5 Add a test for `_render_case_status` in `test_score.py` (or a new test file): assert `repeats=3, passed_runs=3` renders `"3/3 ✓"` and `repeats=3, passed_runs=2` renders `"2/3 ✗"` — confirm it fails
- [x] 1.6 Run `uv run pytest task2/tests/test_bench_repeats.py -x` and confirm all new tests are failing for expected reasons (ImportError / AttributeError)

## 2. AggregatedCaseResult Dataclass

- [ ] 2.1 In `task2/scripts/benchmark.py`, add imports: `from typing import Literal, get_args` and `import statistics`
- [ ] 2.2 Define module-level `RepeatStatus = Literal["all_pass", "partial", "all_fail", "skipped"]` and `_VALID_REPEAT_STATUSES: frozenset[str] = frozenset(get_args(RepeatStatus))`
- [ ] 2.3 Define frozen dataclass `AggregatedCaseResult` with all fields from the spec (`id`, `repeat_status`, `repeats`, `passed_runs`, `median_latency_ms`, `p95_latency_ms`, `stddev_usd`, `avg_mechanism_firings`, `status`, `steps`, `usd`, `prompt_tokens`, `completion_tokens`, `latency_ms_total`, `escalations`, `replans`, `cache_events`, `failure_class`, `skip_reason`)
- [ ] 2.4 Implement `__post_init__` that validates `repeat_status in _VALID_REPEAT_STATUSES` and raises `ValueError` on unknown value
- [ ] 2.5 Run `uv run pytest task2/tests/test_bench_repeats.py::test_aggregated_case_result_rejects_unknown_status -x` and confirm it passes

## 3. aggregate_repeats Function

- [ ] 3.1 Implement `aggregate_repeats(case, *, repeats, llm_client, browser) -> AggregatedCaseResult` in `benchmark.py` that calls `_run_case` N times sequentially and collects results
- [ ] 3.2 Implement `repeat_status` determination: `"skipped"` if all skipped, `"all_pass"` if all in `_PASS_STATUSES`, `"all_fail"` if none pass, `"partial"` otherwise
- [ ] 3.3 Implement statistics computations: `statistics.median` for `median_latency_ms` and `steps`, `statistics.pstdev` for `stddev_usd`, mean for `avg_mechanism_firings`, p95 using the existing `_percentile` helper (import from `score.py` or inline)
- [ ] 3.4 Set `status` derived field: `"succeeded"` for `all_pass`, `"failed"` for `partial`/`all_fail`, `"skipped"` for skipped
- [ ] 3.5 Run `uv run pytest task2/tests/test_bench_repeats.py -x` and confirm Tests 1 and 2 now pass

## 4. --repeats CLI Flag and results.json

- [ ] 4.1 Add `parser.add_argument("--repeats", type=int, default=1)` to `benchmark.py`'s `main()`
- [ ] 4.2 Add validation: if `args.repeats < 1`, print error to stderr and return exit code 1
- [ ] 4.3 In `main()`, branch on `args.repeats`: when `> 1`, call `aggregate_repeats` per case and serialize with `dataclasses.asdict`; when `== 1`, preserve existing `_run_case` + `CaseResult` path unchanged
- [ ] 4.4 Run `uv run pytest task2/tests/test_bench_repeats.py::test_repeats_zero_exits_nonzero -x` and confirm it passes
- [ ] 4.5 Run all bench-repeats tests: `uv run pytest task2/tests/test_bench_repeats.py -v` and confirm all pass

## 5. Scoreboard Status Column Rendering

- [ ] 5.1 In `task2/scripts/score.py`, add helper function `_render_case_status(case: dict) -> str` that returns `"{passed_runs}/{repeats} ✓"` when `repeats > 1` and `passed_runs == repeats`, `"{passed_runs}/{repeats} ✗"` when `repeats > 1` and partial/all-fail, and `case.get("status", "unknown")` otherwise; handle missing `passed_runs` gracefully (default 0)
- [ ] 5.2 In `generate_scoreboard`, replace the `status` variable used in the per-case table row with the result of `_render_case_status(case)`
- [ ] 5.3 Run `uv run pytest task2/tests/ -k "render_case_status or score" -x` and confirm the new `_render_case_status` tests pass
- [ ] 5.4 Run the full score test suite to verify no regressions: `uv run pytest task2/tests/ -v`

## 6. Lint and Full Test Suite

- [ ] 6.1 Run `uv run ruff check task2/scripts/benchmark.py task2/scripts/score.py task2/tests/test_bench_repeats.py` and fix any lint errors
- [ ] 6.2 Run `uv run ruff format task2/scripts/benchmark.py task2/scripts/score.py task2/tests/test_bench_repeats.py`
- [ ] 6.3 Run `uv run ruff check .` from `task2/` and confirm clean
- [ ] 6.4 Run `uv run pytest task2/tests/ -v` (full suite) and confirm all tests pass with green bar
