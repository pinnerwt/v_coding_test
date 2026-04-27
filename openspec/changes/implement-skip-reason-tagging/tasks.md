## 1. Red — Failing tests for skip_reason on CaseResult

- [x] 1.1 In `task2/tests/test_eval.py`, add test `test_skip_reason_required_when_skipped` that constructs `CaseResult(status="skipped", ..., skip_reason=None)` and asserts `ValueError` is raised — confirm it FAILS (field does not exist yet).
- [x] 1.2 Add test `test_skip_reason_rejects_unknown_value` that constructs `CaseResult(status="skipped", ..., skip_reason="bogus")` and asserts `ValueError` — confirm FAILS.
- [x] 1.3 Add test `test_live_disabled_skip_reason` that calls `run_suite()` with a non-fixture case and `live=False`, reads the `CaseResult`, and asserts `skip_reason == "live_disabled"` — confirm FAILS.
- [x] 1.4 Add test `test_fixture_missing_skip_reason` that calls `run_suite()` with a case that has `fixture_path` set to a non-existent path and asserts `skip_reason == "fixture_missing"` — confirm FAILS.
- [x] 1.5 Run `uv run pytest task2/tests/test_eval.py -k "skip_reason"` from `task2/` and confirm all four new tests fail for the expected reason (AttributeError or AssertionError).

## 2. Green — CaseResult field + __post_init__ enforcement

- [x] 2.1 Add `skip_reason: str | None = None` field to `CaseResult` in `task2/scripts/eval.py` (place after `failure_detail`).
- [x] 2.2 Add `__post_init__` to `CaseResult` (frozen dataclass): validate that when `status == "skipped"`, `skip_reason` is non-`None`; validate that non-`None` values are in the allowed frozenset `{"live_disabled", "infra_unavailable", "fixture_missing", "feature_not_implemented"}`; raise `ValueError` on violation.
- [x] 2.3 Update `_skipped_result()` to accept a `reason: str` parameter and pass it as `skip_reason=reason`; update its call-site in `run_suite()` to pass `"live_disabled"`.
- [x] 2.4 In `run_suite()`, before the existing `if not live and not case.get("fixture", False)` check, add a guard: if `case.get("fixture_path")` is set and `not Path(case["fixture_path"]).exists()`, yield `_skipped_result(case, "fixture_missing")`.
- [x] 2.5 Run `uv run pytest task2/tests/test_eval.py -k "skip_reason"` and confirm all four tests pass.

## 3. Red — Failing tests for Skipped subsection in score.py

- [ ] 3.1 In `task2/tests/test_score.py`, add test `test_skipped_subsection_appears` that calls `generate_scoreboard()` with a results dict containing one skipped case with `skip_reason="live_disabled"` and asserts the output contains `**Skipped** (1 cases)` and `| live_disabled | 1 |` — confirm FAILS.
- [ ] 3.2 Add test `test_skipped_subsection_omitted_when_no_skips` that calls `generate_scoreboard()` with no skipped cases and asserts `**Skipped**` does NOT appear — confirm FAILS (or passes trivially; keep if it drives real behaviour).
- [ ] 3.3 Add test `test_skipped_subsection_old_results_no_skip_reason` that calls `generate_scoreboard()` with a case that has `status="skipped"` but no `skip_reason` key and asserts no exception and no `**Skipped**` row for `None` — confirm FAILS.
- [ ] 3.4 Run `uv run pytest task2/tests/test_score.py -k "skipped"` and confirm failures.

## 4. Green — Skipped subsection in generate_scoreboard()

- [ ] 4.1 In `task2/scripts/score.py`, after the per-case table loop and before the aggregate summary line, collect skip reason counts: `{reason: count}` by iterating `cases` and reading `case.get("skip_reason")`, ignoring `None`.
- [ ] 4.2 If any skipped cases have a non-`None` `skip_reason`, emit `**Skipped** (<total> cases)`, a blank line, `| Skip reason | Count |`, `|---|---|`, then one row per reason in canonical order (live_disabled, infra_unavailable, fixture_missing, feature_not_implemented), then a blank line.
- [ ] 4.3 Run `uv run pytest task2/tests/test_score.py -k "skipped"` and confirm all three tests pass.

## 5. Ruff and full test suite

- [ ] 5.1 Run `uv run ruff check .` from `task2/` and fix any lint errors.
- [ ] 5.2 Run `uv run ruff format .` from `task2/` and verify no diffs remain.
- [ ] 5.3 Run `uv run pytest task2/tests/` from the repo root (or `uv run pytest` from `task2/`) and confirm the full test suite is green, including the pre-existing golden snapshot test (update `sample_results_scoreboard.md` if the scoreboard output changed due to the new subsection).
- [ ] 5.4 If the golden snapshot changed, regenerate it: `uv run python scripts/score.py tests/fixtures/results/sample_results.json > tests/fixtures/results/sample_results_scoreboard.md` from `task2/`.
