## 1. Red — Failing tests first

- [x] 1.1 In `task2/tests/test_trends.py`, add `test_flag_regression_returns_true_for_degrading_series`: construct three synthetic `Run` objects with `pass_rate` values `[1.0, 0.5, 0.0]`, call `flag_regression(runs)`, assert `True`. Run `uv run pytest task2/tests/test_trends.py::test_flag_regression_returns_true_for_degrading_series -x` — confirm it fails with `ImportError` or `AttributeError`.
- [x] 1.2 Add `test_flag_regression_returns_false_for_stable_series`: three `Run` objects with `pass_rate` values `[0.5, 0.55, 0.6]`, assert `flag_regression(runs)` returns `False`. Run and confirm red.
- [x] 1.3 Add `test_flag_regression_returns_false_for_single_run`: one `Run` object, assert `False`. Run and confirm red.
- [x] 1.4 Add `test_flag_regression_emits_warning_in_readme_block` (the full integration test): write three synthetic `results.json` files under `tmp_path` with pass-rates 100 %/50 %/0 %, call `collect_runs` + `write_trends`, read README back, assert `⚠️` and `pass-rate regression detected` (case-insensitive) between TRENDS markers, and that `### Latest run` still appears after the warning. Run and confirm red.
- [x] 1.5 Add `test_flag_regression_no_warning_for_stable`: same structure but pass-rates `[0.5, 0.55, 0.6]`; assert `⚠️` is absent between markers. Run and confirm red.

## 2. Green — Implement flag_regression and warning injection

- [x] 2.1 In `task2/scripts/trends.py`, add module-level constant `REGRESSION_THRESHOLD_PP: int = 5`.
- [x] 2.2 Add `import statistics` to `trends.py` imports.
- [x] 2.3 Implement `flag_regression(runs: list[Run]) -> bool` per spec: return `False` for `len(runs) <= 1`; compute `statistics.median([r.pass_rate for r in runs])`; return `runs[-1].pass_rate < median - REGRESSION_THRESHOLD_PP / 100`.
- [x] 2.4 In `_render_readme_block`, call `flag_regression(runs)` (accepting `runs` as a new parameter — update the signature) and prepend the warning line `> ⚠️ **Pass-rate regression detected** — latest run is >5 pp below the historical median. See `benchmark/_trends/regression_onset.md` for per-case onset branches.` before `render_latest_run_table(...)` when the flag fires.
- [x] 2.5 Update `write_trends` to pass `runs` into `_render_readme_block` (the `runs` list is already available in `write_trends`).
- [x] 2.6 Run `uv run pytest task2/tests/test_trends.py -x` — all five new tests plus existing tests must be green.
- [x] 2.7 Run `uv run ruff check task2/scripts/trends.py task2/tests/test_trends.py` and fix any lint issues.

## 3. Red — Failing test for regression_onset.py

- [x] 3.1 Create `task2/tests/test_regression_onset.py`. Add `test_writes_regressions_section`: build a `tmp_path` benchmark root with two runs — `run_a` where `fixture-heading` passes, `run_b` where it fails — call `scripts.regression_onset.main(["--benchmark-root", str(root), "--output", str(out)])`, read the output file, assert `## Regressions` is present and `fixture-heading` appears in the table. Run and confirm red (`ModuleNotFoundError`).
- [x] 3.2 Add `test_handles_empty_benchmark_root`: call `main` on an empty directory, assert exit code 0 and `## Regressions` heading present in output. Run and confirm red.
- [x] 3.3 Add `test_skips_underscore_dirs`: add `_trends/results.json` alongside `master/results.json`, assert `_trends` does not appear in the output. Run and confirm red.

## 4. Green — Implement regression_onset.py

- [x] 4.1 Create `task2/scripts/regression_onset.py` with `main(argv)` entrypoint and `if __name__ == "__main__"` guard.
- [x] 4.2 Implement argument parsing: `--benchmark-root` (default `benchmark`), `--output` (default `<root>/_trends/regression_onset.md`).
- [x] 4.3 Implement run collection: reuse the same scan-and-sort logic as `collect_runs` in `trends.py` (copy or import `_is_passed`; do NOT import the full `Run` dataclass — only the case dicts are needed here).
- [x] 4.4 Implement per-case classification: iterate sorted runs, track last-passing branch per case ID, detect flip to failing, record onset branch and prior-passing branch.
- [x] 4.5 Implement `write_report(cases_data, output_path)`: emit the three-section markdown schema (Regressions, Never Passed, Stable) with the table columns defined in spec.
- [x] 4.6 Add `__init__.py`-safe module entry: ensure `python -m scripts.regression_onset` works (add to `task2/scripts/` alongside existing scripts — no `__init__.py` changes needed if `scripts/` already has one, otherwise add).
- [x] 4.7 Run `uv run pytest task2/tests/test_regression_onset.py -x` — all three tests must be green.
- [x] 4.8 Run `uv run ruff check task2/scripts/regression_onset.py task2/tests/test_regression_onset.py` and fix lint.

## 5. Generate and check in regression_onset.md

- [x] 5.1 From `task2/`, run `uv run python -m scripts.regression_onset --benchmark-root benchmark` to generate `task2/benchmark/_trends/regression_onset.md`.
- [x] 5.2 Inspect the output: verify `## Regressions` contains rows for `fixture-heading` (onset: `task2-implement-plan-event-trace-writer`) and `fixture-count` (onset: `task2-implement-observe-ax-tree`); verify `## Never Passed` contains `correction-l1-miss-l2-hit`, `drift-submit-form-v1`, `drift-submit-form-v2`, `maintenance-drift-rename-v1`, `maintenance-drift-rename-v2`, and the five live cases (all always skipped).
- [x] 5.3 Stage `task2/benchmark/_trends/regression_onset.md` for commit alongside the script.

## 6. Full test suite green + ruff clean

- [x] 6.1 Run `uv run pytest task2/tests/ -x --ignore=task2/tests/test_live.py` (or equivalent fast subset) — confirm zero failures.
- [x] 6.2 Run `uv run ruff check task2/` — confirm zero issues.
- [x] 6.3 Run `uv run ruff format --check task2/` — confirm no formatting diffs.
