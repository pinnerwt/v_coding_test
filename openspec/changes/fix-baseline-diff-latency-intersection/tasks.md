## 1. Red — failing regression test for intersection semantics

- [x] 1.1 In `task2/tests/test_baseline_diff.py`, add `test_latency_delta_uses_intersection_of_case_ids`: synthetic master with cases `{a: 100ms, b: 200ms, c: 300ms}` and branch with cases `{a: 100ms, b: 200ms, c: 300ms, d: 50ms}` (one new case, all common cases identical). Assert `Δ p50 latency: +0ms` and `Δ p95 latency: +0ms` appear in the output.
- [x] 1.2 Run `uv run pytest task2/tests/test_baseline_diff.py::test_latency_delta_uses_intersection_of_case_ids` from `task2/` and confirm it **fails** (current whole-population code reports a non-zero delta because d=50ms shifts the population).

## 2. Green — implement intersection latency aggregation

- [x] 2.1 In `task2/scripts/baseline_diff.py::generate_diff_markdown`, replace the whole-population latency lists (`m_lat`, `b_lat`) with intersection-filtered lists: compute `common_ids = set(master_cases) & set(branch_cases)`, then build `m_lat = [master_cases[cid].get("latency_ms_total", 0) for cid in common_ids]` and `b_lat = [branch_cases[cid].get("latency_ms_total", 0) for cid in common_ids]`.
- [x] 2.2 Guard the latency delta lines: if `common_ids` is empty, emit `Δ p50 latency: —` and `Δ p95 latency: —` instead of calling `_percentile`.
- [x] 2.3 Add the "Cases" annotation line immediately after the `Δ p95 latency` line: compute `n_common = len(common_ids)`, `n_added = len(set(branch_cases) - set(master_cases))`, `n_dropped = len(set(master_cases) - set(branch_cases))`, then append `f"Cases: {n_common} common, +{n_added} added, -{n_dropped} dropped"`.
- [x] 2.4 Run `uv run pytest task2/tests/test_baseline_diff.py::test_latency_delta_uses_intersection_of_case_ids` and confirm it **passes**.

## 3. Cases annotation — write and verify test

- [x] 3.1 Add `test_cases_annotation_reflects_added_case` in `task2/tests/test_baseline_diff.py`: master `{a, b, c}` + branch `{a, b, c, d}` — assert `Cases: 3 common, +1 added, -0 dropped` in output.
- [x] 3.2 Add `test_cases_annotation_all_zeros_for_identical_runs`: master and branch identical — assert `Cases: 2 common, +0 added, -0 dropped` (use a two-case fixture).
- [x] 3.3 Run both new tests and confirm they pass.

## 4. Red + Green — empty intersection sentinel

- [x] 4.1 Add `test_latency_delta_empty_intersection_renders_dash` in `task2/tests/test_baseline_diff.py`: master `{a: 100ms, b: 200ms}` + branch `{c: 300ms, d: 400ms}` (no common ids). Assert output contains `Δ p50 latency: —` and `Δ p95 latency: —` and `Cases: 0 common, +2 added, -2 dropped`.
- [x] 4.2 Run the test and confirm it passes (step 2.2 already implements this).

## 5. Existing test hygiene — review and align

- [ ] 5.1 Read `test_aggregate_latency_delta_negative` (lines 115–134 of `task2/tests/test_baseline_diff.py`): master `{c1: 1000ms, c2: 2000ms}` + branch `{c1: 500ms, c2: 1500ms}` — case ids match, so intersection == whole-population; the test continues to pass unchanged. Confirm by running it.
- [ ] 5.2 Scan the rest of `task2/tests/test_baseline_diff.py` for any other latency delta assertions that implicitly assumed whole-population semantics with differing case sets. If found, update them to match intersection semantics or add a comment marking them as intersection-equal-to-whole-population cases.
- [ ] 5.3 Run the full test suite: `uv run pytest task2/tests/test_baseline_diff.py` — all tests must pass.

## 6. Linting and final check

- [ ] 6.1 Run `uv run ruff check .` from `task2/` — must be clean (no errors or warnings).
- [ ] 6.2 Run `uv run ruff format .` from `task2/` and commit any formatting-only changes.
- [ ] 6.3 Run the full `task2/` test suite one final time: `uv run pytest` — green bar required before marking this change done.
