# score-script Specification

## Purpose
TBD - created by archiving change implement-quantitative-eval. Update Purpose after archive.

## Requirements

### Requirement: score.py reads a results JSON and emits a markdown scoreboard

`scripts/score.py` SHALL be a standalone script (invocable via `uv run python -m scripts.score` or `uv run python scripts/score.py`) that:

1. Accepts a positional `results_file` argument (path to `eval/results/<ts>.json`). When omitted, it SHALL default to the most-recently modified file in `eval/results/`.
2. Reads and validates the results JSON.
3. Emits a markdown scoreboard to stdout (or to a file via `--output`).

The scoreboard SHALL contain all of the following sections, in order:

- **Per-case status table**: columns `Case`, `Status`, `Steps`, `Latency (ms)`, `USD`, `Tokens (P+C)`, `Escalations`, `Replans`, `Cache Inv.`
- **Summary line**: `N/M succeeded (X%)` where N = passed (succeeded + unverified), M = total non-skipped.
- **Latency percentiles**: `p50: Xms  p95: Xms` computed over `latency_ms_total` values of non-skipped cases.
- **Totals**: `Total USD: $X.XXXX   Total tokens: P prompt + C completion`.
- **Locator-tier mix**: table of tier name → count across all cases, rendered as `| Tier | Count |`.
- **Mechanism firing rates**: table rendered as `| Mechanism | Cases with ≥1 firing |` with rows for `L1→L2 escalation`, `Replan`, and `Cache invalidation`, each showing `N/M` (non-skipped cases with at least one firing / total non-skipped).

#### Scenario: score.py reads the fixture results file and produces non-empty markdown

- **GIVEN** `tests/fixtures/results/sample_results.json` exists with at least two case entries (one succeeded, one failed) and non-zero metrics
- **WHEN** `score.py tests/fixtures/results/sample_results.json` is invoked
- **THEN** stdout SHALL contain a markdown table with at least one `|` row per case
- **AND** stdout SHALL contain the string `succeeded`
- **AND** stdout SHALL contain `p50:`
- **AND** stdout SHALL contain `Escalations`
- **AND** stdout SHALL contain `Mechanism firing rates`

#### Scenario: score.py output matches golden snapshot

- **GIVEN** `tests/fixtures/results/sample_results.json` is a vendored fixture with known content
- **WHEN** `score.py tests/fixtures/results/sample_results.json` is invoked
- **THEN** stdout SHALL match `tests/fixtures/results/sample_results_scoreboard.md` character-for-character (after stripping trailing whitespace per line)

#### Scenario: Latency percentile computation is correct

- **GIVEN** a results file with three non-skipped cases with `latency_ms_total` values `[100, 200, 800]`
- **WHEN** `score.py` computes percentiles
- **THEN** p50 SHALL equal `200` and p95 SHALL equal `800` (nearest-rank method, ceiling index)

#### Scenario: Skipped cases are excluded from success rate and percentiles

- **GIVEN** a results file with one `succeeded` case and one `skipped` case
- **WHEN** `score.py` computes the summary line
- **THEN** the denominator M SHALL equal `1` (not `2`)
- **AND** the skipped case SHALL NOT contribute to latency percentile computation

#### Scenario: Mechanism rates block is backward-compatible with old results missing mechanism fields

- **GIVEN** a results file whose case objects have no `escalations`, `replans`, or `cache_events` keys
- **WHEN** `score.py` emits the scoreboard
- **THEN** the mechanism columns SHALL default to `0` and the firing rate rows SHALL show `0/M`
- **AND** no exception SHALL be raised

### Requirement: score.py --update-readme splices scoreboard into README

When `--update-readme` is passed (with `--readme-path` defaulting to `task2/README.md`), `score.py` SHALL splice the generated scoreboard between sentinel comments in the README:

```
<!-- SCOREBOARD:BEGIN -->
...generated markdown...
<!-- SCOREBOARD:END -->
```

If the sentinels are absent, `score.py` SHALL append the scoreboard as a new `## Live eval results` section.

The splice SHALL be idempotent: running `--update-readme` twice SHALL produce the same README content as running it once.

#### Scenario: --update-readme replaces content between sentinels

- **GIVEN** `task2/README.md` contains `<!-- SCOREBOARD:BEGIN -->` and `<!-- SCOREBOARD:END -->` with stale content between them
- **WHEN** `score.py <results_file> --update-readme` is invoked
- **THEN** the README content between the sentinels SHALL be replaced with the newly generated scoreboard
- **AND** content outside the sentinels SHALL be unchanged

#### Scenario: --update-readme is idempotent

- **WHEN** `score.py <results_file> --update-readme` is invoked twice on the same results file
- **THEN** the README content SHALL be identical after both invocations

### Requirement: score.py --latest uses most-recent results file

When no positional `results_file` is supplied, `score.py` SHALL automatically use the most recently modified file in `eval/results/` (sorted by `mtime`, descending).

#### Scenario: No argument defaults to latest file

- **GIVEN** `eval/results/` contains `20260101_120000.json` and `20260426_032729.json`
- **WHEN** `score.py` is invoked with no positional argument
- **THEN** it SHALL read `20260426_032729.json` (the more recent file)
