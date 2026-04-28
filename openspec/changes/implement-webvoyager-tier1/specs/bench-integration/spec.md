## ADDED Requirements

### Requirement: Bench runner selects task path by --tier flag
`scripts/bench.py` SHALL accept a `--tier` argument (integer, choices `[0, 1]`, default `0`) that selects the task source path for a given suite:

- Tier 0 maps to the existing Tier-0 fixture (`tests/fixtures/benchmarks/webvoyager/tasks_sample.json`).
- Tier 1 maps to the new Tier-1 dataset (`eval/bench/data/webvoyager/tier1.json`).

The `WEBVOYAGER_TASKS` environment variable SHALL continue to override the resolved path regardless of `--tier`, preserving the existing env-var escape hatch.

#### Scenario: Default tier is 0 and selects Tier-0 fixture
- **WHEN** `main(["--suite", "webvoyager"])` is called without `--tier` and without `WEBVOYAGER_TASKS` set
- **THEN** the loader is called with a path ending in `tests/fixtures/benchmarks/webvoyager/tasks_sample.json`

#### Scenario: --tier 1 selects the Tier-1 dataset
- **WHEN** `main(["--suite", "webvoyager", "--tier", "1"])` is called without `WEBVOYAGER_TASKS` set
- **THEN** the loader is called with a path ending in `eval/bench/data/webvoyager/tier1.json`

#### Scenario: WEBVOYAGER_TASKS env var overrides --tier 1
- **WHEN** `main(["--suite", "webvoyager", "--tier", "1"])` is called with `WEBVOYAGER_TASKS` set to a custom path
- **THEN** the loader is called with that custom path, not the Tier-1 default path
