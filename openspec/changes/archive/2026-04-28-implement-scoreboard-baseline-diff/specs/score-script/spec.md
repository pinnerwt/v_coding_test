## ADDED Requirements

### Requirement: score.py --diff appends baseline diff block to scoreboard output

`scripts/score.py` SHALL accept an optional `--diff` argument (path to a baseline `results.json` file). When provided:

1. After generating the main scoreboard, call `baseline_diff.generate_diff_markdown(baseline_data, branch_data)` and append the result to the scoreboard output (separated by a blank line and a `---` horizontal rule).
2. When `--output` is also provided, write the combined scoreboard + diff to the output file.
3. When `--diff` is NOT provided, behaviour is unchanged from the current implementation.
4. When the path provided to `--diff` does not exist, `score.py` SHALL print an error to stderr and exit with code 1.

This flag is optional convenience for local use; the canonical diff output is `diff.md` written by `benchmark.py`.

#### Scenario: --diff flag appends diff block to scoreboard

- **GIVEN** `tests/fixtures/results/sample_results.json` exists (branch data)
- **AND** `tests/fixtures/results/master_results.json` exists (baseline data)
- **WHEN** `score.py tests/fixtures/results/sample_results.json --diff tests/fixtures/results/master_results.json` is invoked
- **THEN** stdout SHALL contain the normal scoreboard content (category summary, per-case table, summary line)
- **AND** stdout SHALL also contain a `---` separator followed by the diff output
- **AND** stdout SHALL contain `Δ vs master` (or similar heading from `generate_diff_markdown`)

#### Scenario: --diff with non-existent path exits with error

- **GIVEN** the path passed to `--diff` does not exist on disk
- **WHEN** `score.py <results_file> --diff /nonexistent/path.json` is invoked
- **THEN** stderr SHALL contain an error message referencing the missing file
- **AND** the exit code SHALL be 1

#### Scenario: omitting --diff leaves scoreboard unchanged

- **GIVEN** `tests/fixtures/results/sample_results.json` exists
- **WHEN** `score.py tests/fixtures/results/sample_results.json` is invoked without `--diff`
- **THEN** stdout SHALL NOT contain `Δ vs master`
- **AND** the output SHALL be identical to the baseline scoreboard output
