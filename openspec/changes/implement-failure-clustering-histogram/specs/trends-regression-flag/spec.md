## ADDED Requirements

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
