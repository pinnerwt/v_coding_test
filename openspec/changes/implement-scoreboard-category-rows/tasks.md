## 1. Vendored Fixture

- [ ] 1.1 Create `task2/tests/fixtures/score_categories_results.json` with at least three cases: one `drift-submit-form-v1` with `status: "failed"`, one `fixture-login-v1` with `status: "succeeded"`, and one `live-search-v1` with `status: "skipped"`. Include minimal required fields (`id`, `status`, `steps`, `latency_ms_total`, `usd`, `prompt_tokens`, `completion_tokens`). Run `uv run ruff check .` from `task2/` — no new Python yet, just verify the fixture is valid JSON.

## 2. Failing Tests (Red)

- [ ] 2.1 In `task2/tests/test_score.py`, add `test_suite_thresholds_importable`: import `SUITE_THRESHOLDS` from `scripts.score` and assert keys `"drift"`, `"fixture"`, `"live"` are present, `target_pct` values are 100/80/60, and `"correction-"` and `"maintenance-drift-"` are in `SUITE_THRESHOLDS["drift"]["id_prefixes"]`. Run `uv run pytest tests/test_score.py::test_suite_thresholds_importable -x` — confirm `ImportError` or `AttributeError` (red).

- [ ] 2.2 In `task2/tests/test_score.py`, add `test_category_summary_passing_fixture`: load `tests/fixtures/score_categories_results.json`, call `generate_scoreboard(data)`, assert the output contains `"Fixture: 1/1 (100%) [target 80%] ✅"`. Run the test — confirm failure (red).

- [ ] 2.3 Add `test_category_summary_failing_drift`: same fixture, assert output contains `"Drift suite: 0/1 (0%) [target 100%] ❌"`. Run — confirm failure (red).

- [ ] 2.4 Add `test_category_summary_skipped_live`: same fixture, assert output contains `"Live: 0/0 ran [target 60%] ⏭️"`. Run — confirm failure (red).

- [ ] 2.5 Add `test_category_summary_before_per_case_table`: same fixture, assert the position of `"Drift suite:"` in the output string is less than the position of the first `"| "` character that begins the per-case table header. Run — confirm failure (red).

## 3. Minimal Implementation (Green)

- [ ] 3.1 Add `SUITE_THRESHOLDS` module-level constant to `task2/scripts/score.py` with the three required suite entries (drift/fixture/live), exactly as specified in the design. Run `test_suite_thresholds_importable` — confirm green.

- [ ] 3.2 In `generate_scoreboard()`, add a `_bucket_cases_by_suite()` helper (or inline logic) that iterates cases, matches each `case["id"]` against suite `id_prefixes` in insertion order, and returns a dict mapping suite key → list of cases. Cases not matching any suite are silently dropped from the summary (not rendered). Run `uv run ruff check .` from `task2/` — fix any lint errors.

- [ ] 3.3 In `generate_scoreboard()`, before appending the per-case table header, build and prepend the category summary lines. For each suite in `SUITE_THRESHOLDS` insertion order: compute `ran = len([c for c in suite_cases if c["status"] != "skipped"])`, `passed = len([c for c in suite_cases if c["status"] in ("succeeded", "unverified")])`, and choose the glyph. When `ran == 0` emit `"<name>: 0/0 ran [target <target_pct>%] ⏭️"`; otherwise emit `"<name>: <passed>/<ran> (<pct>%) [target <target_pct>%] <glyph>"`. Append a blank line after all suite rows. Run all four category tests — confirm green.

- [ ] 3.4 Run `test_category_summary_before_per_case_table` — confirm green.

- [ ] 3.5 Run the full test suite: `uv run pytest tests/test_score.py -x`. Confirm all previously passing tests still pass (no regressions). If `test_score_output_matches_golden_snapshot` fails due to the new summary rows, update `tests/fixtures/results/sample_results_scoreboard.md` to include the new category lines at the top.

## 4. Lint and Final Checks

- [ ] 4.1 Run `uv run ruff check .` and `uv run ruff format .` from `task2/`. Fix any issues. Re-run the full test suite to confirm still green.

- [ ] 4.2 Verify no docstrings or comments were introduced in `task2/scripts/score.py` production code (per CLAUDE.md). Remove any that were accidentally added.
