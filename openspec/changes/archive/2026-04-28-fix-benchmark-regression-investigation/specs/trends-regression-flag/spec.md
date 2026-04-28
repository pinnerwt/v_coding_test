## ADDED Requirements

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
