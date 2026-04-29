# trends-regression-flag Specification

## Purpose

Detect when the latest benchmark run's pass-rate is materially below the running median, and surface a visible warning in the auto-generated `<!-- TRENDS:BEGIN -->` block of `task2/README.md`. This turns the trend SVGs from passive charts into an actionable signal so regressions are noticed in PR review rather than weeks later.

## Requirements

### Requirement: flag_regression pure helper
`task2/scripts/trends.py` SHALL export a pure function `flag_regression(runs: list[Run]) -> bool` that:

1. Returns `False` when `runs` is empty or has exactly one entry (no meaningful baseline to compare against).
2. Computes the median of `r.pass_rate` across all entries in `runs`.
3. Returns `True` when `runs[-1].pass_rate < median - REGRESSION_THRESHOLD_PP / 100`, where `REGRESSION_THRESHOLD_PP: int = 5` is a module-level constant in `trends.py`.
4. Returns `False` otherwise.

The function SHALL NOT perform any file I/O, network calls, or logging. It SHALL be importable and callable in unit tests without any filesystem setup.

#### Scenario: Returns False for empty runs list
- **WHEN** `flag_regression([])` is called
- **THEN** it SHALL return `False`

#### Scenario: Returns False for single-run list
- **WHEN** `flag_regression([run_at_50pct])` is called with a single `Run` whose `pass_rate` is `0.5`
- **THEN** it SHALL return `False`

#### Scenario: Returns True when latest is more than 5pp below median
- **GIVEN** three `Run` objects with `pass_rate` values `[1.0, 0.5, 0.0]` (monotonically degrading)
- **WHEN** `flag_regression(runs)` is called
- **THEN** median pass-rate is `0.5`, latest is `0.0`, delta is `50pp > 5pp`
- **AND** the function SHALL return `True`

#### Scenario: Returns False when latest equals median minus exactly 5pp
- **GIVEN** three `Run` objects with `pass_rate` values `[0.6, 0.5, 0.45]`
- **WHEN** `flag_regression(runs)` is called
- **THEN** median is `0.5`, latest is `0.45`, delta is `5pp` (not strictly greater)
- **AND** the function SHALL return `False`

#### Scenario: Returns False when latest is above median
- **GIVEN** three `Run` objects with `pass_rate` values `[0.2, 0.3, 0.8]`
- **WHEN** `flag_regression(runs)` is called
- **THEN** latest is above median
- **AND** the function SHALL return `False`

### Requirement: Regression warning line in TRENDS block
When `write_trends` renders the `<!-- TRENDS:BEGIN … TRENDS:END -->` block in `task2/README.md` and `flag_regression(runs)` returns `True`, `trends.py` SHALL inject a warning line in the rendered block **before** the latest-run table (i.e., before the `### Latest run —` heading produced by `render_latest_run_table`).

The warning line SHALL contain `⚠️` and the text `Pass-rate regression detected` (case-insensitive match acceptable for tests). When `flag_regression(runs)` returns `False`, no warning line SHALL appear.

The warning MUST be emitted only inside the `<!-- TRENDS:BEGIN -->` block, not elsewhere in the README.

#### Scenario: Warning emitted in block when regression detected
- **GIVEN** three benchmark run directories with pass-rates `[1.0, 0.5, 0.0]` (synthetic)
- **WHEN** `write_trends(runs, out_dir=..., readme_path=readme, benchmark_root=...)` is called
- **THEN** the README content between `<!-- TRENDS:BEGIN -->` and `<!-- TRENDS:END -->` SHALL contain `⚠️`
- **AND** SHALL contain the substring `Pass-rate regression detected` (case-insensitive)
- **AND** the warning SHALL appear before `### Latest run`

#### Scenario: No warning when pass-rate is stable
- **GIVEN** three benchmark run directories with pass-rates `[0.5, 0.55, 0.6]` (improving)
- **WHEN** `write_trends(runs, out_dir=..., readme_path=readme, benchmark_root=...)` is called
- **THEN** the README content between the TRENDS markers SHALL NOT contain `⚠️`

#### Scenario: No warning when only one run exists
- **GIVEN** exactly one benchmark run directory
- **WHEN** `write_trends` is called
- **THEN** the README SHALL NOT contain a regression warning

### Requirement: Deterministic test for regression flag in test_trends.py
`task2/tests/test_trends.py` SHALL contain a test named `test_flag_regression_emits_warning_in_readme_block` that:

1. Constructs a synthetic 3-run benchmark directory tree under `tmp_path` with monotonically degrading pass-rates (e.g., 100 %, 50 %, 0 %).
2. Creates a stub `README.md` containing `<!-- TRENDS:BEGIN -->` / `<!-- TRENDS:END -->` markers.
3. Calls `collect_runs` then `write_trends` with `readme_path` and `benchmark_root`.
4. Reads back the README and asserts:
   - The `⚠️` character appears between the two TRENDS markers.
   - The string `Pass-rate regression detected` (case-insensitive) appears between the markers.
   - `<!-- TRENDS:BEGIN -->` and `<!-- TRENDS:END -->` are both still present.
   - Surrounding README content outside the block is unchanged.

The test SHALL use only the `tmp_path` fixture (no real filesystem reads, no LLM calls).

#### Scenario: Test is deterministic and does not require network or LLM
- **WHEN** `test_flag_regression_emits_warning_in_readme_block` is executed in isolation with `pytest`
- **THEN** it SHALL pass without network access, environment variables, or a running Qwen endpoint
- **AND** it SHALL produce no side effects outside `tmp_path`

### Requirement: failure_classes stacked-area SVG

`task2/scripts/trends.py` SHALL emit a stacked-area SVG `task2/benchmark/_trends/failure_classes.svg` each time `write_trends(...)` is called. The SVG visualises per-`failure_class` failure counts across all benchmark runs.

**Data collection:**

A new function `collect_failure_class_runs(benchmark_root: Path) -> list[dict[str, int]]` SHALL be added to `trends.py`. It SHALL:

1. Scan run directories in the same order as `collect_runs` (ascending by `run_at`, skipping `_`-prefixed directories).
2. For each run, count non-skipped cases grouped by their non-None `failure_class` value.
3. Return a list (one dict per run, in the same positional order as the `list[Run]` returned by `collect_runs`) where each dict maps `failure_class` string → count. Runs with no failures produce an empty dict `{}`.

**Chart rendering:**

A new function `render_failure_classes_svg(runs: list[Run], class_counts: list[dict[str, int]]) -> str` SHALL be added to `trends.py`. It SHALL:

1. Collect all distinct `failure_class` keys across all dicts in `class_counts`.
2. Sort the classes alphabetically to produce a deterministic series order.
3. Assign colors from a fixed palette list in sorted-class-index order (modulo palette length), so the same class always receives the same color across runs.
4. Render a stacked-area chart where each class is one filled polygon. For each run `i`, the stacked y-values are the cumulative sums of counts in sorted-class order.
5. Include a legend mapping class name to color, positioned consistently with existing charts.
6. When `runs` is empty or all `class_counts` dicts are empty, return the result of `_empty_svg("Failure classes")`.
7. **Single-run rendering**: when `len(runs) == 1` AND at least one class has a non-zero count, each per-class polygon SHALL have non-zero geometric area (i.e. it MUST render as a visible filled shape, not collapse to a zero-area degenerate polygon). The per-class cumulative y-coordinates SHALL match the `n >= 2` cumulative-stacking math. The exact horizontal layout (bar position, bar width) is a non-normative implementation detail.

**Integration with `write_trends`:**

`write_trends(runs, *, out_dir, readme_path=None, benchmark_root=None)` SHALL:

1. Call `collect_failure_class_runs(benchmark_root)` (when `benchmark_root` is not None) or compute from the same run-discovery scan.
2. Write `render_failure_classes_svg(runs, class_counts)` to `out_dir / "failure_classes.svg"`.

**README TRENDS block:**

`_render_readme_block` SHALL include a fourth image reference line after the cost chart line:

- `![Failure classes over time](benchmark/_trends/failure_classes.svg)`

This line SHALL appear after the `![Cost by status](benchmark/_trends/cost.svg)` line and before the explanatory prose paragraph.

#### Scenario: write_trends writes failure_classes.svg to the output directory

- **GIVEN** a `benchmark_root` containing at least one run directory with a `results.json` whose cases include failed cases with non-None `failure_class` values
- **WHEN** `write_trends(runs, out_dir=out_dir, readme_path=None, benchmark_root=benchmark_root)` is called
- **THEN** `out_dir / "failure_classes.svg"` SHALL exist and be a non-empty string starting with `<svg`

#### Scenario: failure_classes SVG is a valid stacked-area chart with one series per class

- **GIVEN** two synthetic runs where run 1 has `{"supervisor_halt": 3, "locator_miss": 1}` and run 2 has `{"supervisor_halt": 1, "tool_error": 2}`
- **WHEN** `render_failure_classes_svg(runs, class_counts)` is called
- **THEN** the returned string SHALL contain `supervisor_halt` (in legend text or title)
- **AND** SHALL contain `locator_miss`
- **AND** SHALL contain `tool_error`
- **AND** the string SHALL be valid SVG (starts with `<svg`, ends with `</svg>`)

#### Scenario: Failure-class colors are deterministic across runs

- **GIVEN** two separate calls to `render_failure_classes_svg` with the same set of class names but different count values
- **WHEN** both SVG strings are inspected
- **THEN** the color assigned to each class name SHALL be identical across both calls

#### Scenario: failure_classes SVG is the empty placeholder when no failures exist

- **GIVEN** runs where all `class_counts` dicts are empty (no failed cases)
- **WHEN** `render_failure_classes_svg(runs, class_counts)` is called
- **THEN** the returned SVG SHALL contain the text `Failure classes: no data`

#### Scenario: write_trends writes failure_classes.svg even when benchmark_root is None

- **GIVEN** `runs` is a non-empty list and `class_counts` is computed externally
- **WHEN** `write_trends(runs, out_dir=out_dir, readme_path=None, benchmark_root=None)` is called
- **THEN** `out_dir / "failure_classes.svg"` SHALL exist (using an empty class_counts list when benchmark_root is None)

#### Scenario: README TRENDS block contains failure_classes.svg image row

- **GIVEN** a README with `<!-- TRENDS:BEGIN -->` and `<!-- TRENDS:END -->` markers
- **WHEN** `write_trends(runs, out_dir=out_dir, readme_path=readme, benchmark_root=benchmark_root)` is called
- **THEN** the README content between the TRENDS markers SHALL contain `benchmark/_trends/failure_classes.svg`
- **AND** that image reference SHALL appear after the `benchmark/_trends/cost.svg` reference

#### Scenario: Single-run failure_classes SVG renders visible non-zero-area polygons

- **GIVEN** a single run (`len(runs) == 1`) and a single non-empty class_counts dict (e.g. `[{"alpha": 2, "beta": 3}]`)
- **WHEN** `render_failure_classes_svg(runs, class_counts)` is called
- **THEN** every `<polygon>` element in the returned SVG SHALL have non-zero geometric area (computed via the shoelace formula over its `points` list)
- **AND** each polygon's y-coordinates SHALL match the cumulative-stacking math used for `n >= 2` (the per-class top y is `cum + count`, the bottom y is `cum`)
