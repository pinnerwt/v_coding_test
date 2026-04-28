## MODIFIED Requirements

### Requirement: benchmark --repeats N CLI flag

`scripts/benchmark.py`, invoked as `uv run python -m scripts.benchmark`, SHALL accept a new optional argument `--repeats N` (type `int`, default `1`). When `N == 1` the behavior SHALL be identical to the current single-run behavior. When `N > 1` each case is executed N times sequentially and the results are aggregated into a single `AggregatedCaseResult` per case before being written to the output JSON.

The CI workflow SHALL document that it passes `--repeats 3` for the drift suite; the default of `1` is preserved for all other callers. (The forward reference to "canary suites" is removed — the canary suite is now implemented and its gate logic is handled by `scripts.canary_gate`, not by `--repeats`.)

#### Scenario: --repeats 1 is the default and preserves existing behavior

- **WHEN** `scripts.benchmark.main([])` is called without `--repeats`
- **THEN** each case is executed exactly once
- **AND** the results JSON shape is identical to the pre-feature shape

#### Scenario: --repeats 3 causes each case to run three times

- **GIVEN** a suite with one fixture case and `_run_case` patched to return a deterministic `CaseResult`
- **WHEN** `scripts.benchmark.main(["--repeats", "3"])` is called
- **THEN** `_run_case` is called exactly 3 times for that case
- **AND** the results JSON contains exactly one aggregated entry for the case

#### Scenario: --repeats value is validated as a positive integer

- **WHEN** `scripts.benchmark.main(["--repeats", "0"])` is called
- **THEN** the process SHALL exit with a non-zero code and print an error message
