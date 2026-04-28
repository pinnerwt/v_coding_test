## 1. Red — histogram header test

- [x] 1.1 In `task2/tests/test_score.py`, add `test_failure_histogram_header_present`: given a results dict with one failed case having `failure_class="supervisor_halt"`, assert `generate_scoreboard(data)` contains `**Failure histogram**` and `| Failure class | Count |`. Run `uv run pytest tests/test_score.py::test_failure_histogram_header_present` — confirm it fails (AttributeError or assertion error).

## 2. Red — histogram counts and sort-order tests

- [x] 2.1 Add `test_failure_histogram_counts_sorted_desc`: five failed cases (3× `supervisor_halt`, 1× `locator_miss`, 1× `tool_error`). Assert output contains `| supervisor_halt | 3 |` and that `supervisor_halt` appears before `locator_miss` / `tool_error`. Run — confirm failure.
- [x] 2.2 Add `test_failure_histogram_ties_sorted_alpha`: two failed cases with `locator_miss` and `tool_error` (count=1 each). Assert `locator_miss` appears before `tool_error` in the histogram output. Run — confirm failure.

## 3. Red — histogram suppression tests

- [x] 3.1 Add `test_failure_histogram_suppressed_no_failures`: all cases `succeeded`. Assert output does NOT contain `**Failure histogram**`. Run — confirm failure.
- [x] 3.2 Add `test_failure_histogram_suppressed_all_none`: one failed case with `failure_class=None`. Assert output does NOT contain `**Failure histogram**`. Run — confirm failure.
- [x] 3.3 Add `test_failure_histogram_backward_compat_no_key`: case dicts have no `failure_class` key. Assert output does NOT contain `**Failure histogram**` and no exception is raised. Run — confirm failure.

## 4. Red — histogram placement test

- [x] 4.1 Add `test_failure_histogram_placement`: results with category summary cases and one failed case with `failure_class="locator_miss"`. Assert position of `**Failure histogram**` is after the category summary text and before the `| Case |` header row in the output string. Run — confirm failure.

## 5. Green — implement histogram block in score.py

- [x] 5.1 In `task2/scripts/score.py`, add a `_render_failure_histogram(cases: list[dict]) -> str` helper that: collects `failure_class` values from failed (non-skipped, non-passed) cases, counts and sorts desc-by-count with alpha tie-break, renders the `**Failure histogram**` header and markdown table, returns empty string when count total is zero.
- [x] 5.2 In `generate_scoreboard`, splice the histogram block into the output after the category summary lines and before the per-case table header. Run all histogram tests — confirm green.

## 6. Green — update golden snapshot fixture

- [x] 6.1 Run `uv run python -m scripts.score tests/fixtures/results/sample_results.json` from `task2/` and inspect whether the fixture's failed case has a `failure_class` set. If yes, regenerate `tests/fixtures/results/sample_results_scoreboard.md` to include the new histogram block. If the fixture's failed case has `failure_class=null`, add a `failure_class` to the fixture's failed case and regenerate the snapshot. Run `uv run pytest tests/test_score.py` — confirm the golden-snapshot test passes.

## 7. Red — trends collect_failure_class_runs test

- [x] 7.1 In `task2/tests/test_trends.py`, add `test_collect_failure_class_runs_basic`: create two synthetic run directories under `tmp_path` with `results.json` files containing failed cases with known `failure_class` values. Assert `collect_failure_class_runs(benchmark_root)` returns a list of two dicts with correct counts and correct run order. Run — confirm failure.
- [x] 7.2 Add `test_collect_failure_class_runs_excludes_none`: a run with one failed case having `failure_class=null`. Assert the returned dict for that run is `{}` (no `None` key). Run — confirm failure.

## 8. Red — render_failure_classes_svg test

- [x] 8.1 Add `test_render_failure_classes_svg_basic`: call `render_failure_classes_svg(runs, class_counts)` with two synthetic runs and known class_counts. Assert returned string is valid SVG (starts with `<svg`, ends with `</svg>`), contains class names in legend, is non-empty. Run — confirm failure.
- [x] 8.2 Add `test_render_failure_classes_svg_empty`: call with empty class_counts list. Assert returned SVG contains `Failure classes: no data`. Run — confirm failure.
- [x] 8.3 Add `test_render_failure_classes_svg_deterministic_colors`: call twice with same class names, different counts. Assert the color assigned to each class is identical across both calls. Run — confirm failure.

## 9. Red — write_trends emits failure_classes.svg

- [x] 9.1 Add `test_write_trends_writes_failure_classes_svg`: set up `tmp_path` with a benchmark root containing one run dir. Call `write_trends(runs, out_dir=out_dir, benchmark_root=bench_root)`. Assert `out_dir / "failure_classes.svg"` exists and content starts with `<svg`. Run — confirm failure.

## 10. Red — README TRENDS block gains failure_classes row

- [x] 10.1 Add `test_write_trends_readme_includes_failure_classes_svg`: set up stub README with TRENDS markers. Call `write_trends` with `readme_path`. Assert README between markers contains `benchmark/_trends/failure_classes.svg` and that it appears after `benchmark/_trends/cost.svg`. Run — confirm failure.

## 11. Green — implement collect_failure_class_runs, render_failure_classes_svg, write_trends update

- [x] 11.1 Add `collect_failure_class_runs(benchmark_root: Path) -> list[dict[str, int]]` to `task2/scripts/trends.py` using the same run-discovery loop as `collect_runs`, extracting `failure_class` counts from each `results.json`.
- [x] 11.2 Add `render_failure_classes_svg(runs: list[Run], class_counts: list[dict[str, int]]) -> str` to `trends.py` implementing the stacked-area SVG with deterministic color assignment from a fixed palette.
- [x] 11.3 Update `write_trends` to call `collect_failure_class_runs` (when `benchmark_root` is not None) and write `failure_classes.svg` to `out_dir`.
- [x] 11.4 Update `_render_readme_block` to include the `![Failure classes over time](benchmark/_trends/failure_classes.svg)` line after the cost SVG line. Run all trends tests — confirm green.

## 12. Ruff / format gate

- [x] 12.1 From `task2/`, run `uv run ruff check .` — fix any lint errors reported.
- [x] 12.2 Run `uv run ruff format .` — apply formatting.
- [x] 12.3 Run `uv run pytest` — confirm full test suite is green with no regressions.
