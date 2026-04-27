## MODIFIED Requirements

### Requirement: score.py reads a results JSON and emits a markdown scoreboard

`scripts/score.py` SHALL be a standalone script (invocable via `uv run python -m scripts.score` or `uv run python scripts/score.py`) that:

1. Accepts a positional `results_file` argument (path to `eval/results/<ts>.json`). When omitted, it SHALL default to the most-recently modified file in `eval/results/`.
2. Reads and validates the results JSON.
3. Emits a markdown scoreboard to stdout (or to a file via `--output`).

The scoreboard SHALL contain all of the following sections, in order:

- **Category summary**: one line per suite in `SUITE_THRESHOLDS` insertion order, rendered BEFORE the per-case table. Each line SHALL follow the format: `<SuiteName>: <passed>/<ran> (<pct>%) [target <target>%] <glyph>` where `<glyph>` is ✅ when passed/ran >= target_pct and ran > 0, ❌ when passed/ran < target_pct and ran > 0, or ⏭️ when ran == 0. Cases not matching any suite prefix SHALL be omitted from the category summary (not shown as "other" row).
- **Per-case status table**: columns `Case`, `Status`, `Steps`, `Latency (ms)`, `USD`, `Tokens (P+C)`, `Escalations`, `Replans`, `Cache Inv.`
- **Summary line**: `N/M succeeded (X%)` where N = passed (succeeded + unverified), M = total non-skipped.
- **Latency percentiles**: `p50: Xms  p95: Xms` computed over `latency_ms_total` values of non-skipped cases.
- **Totals**: `Total USD: $X.XXXX   Total tokens: P prompt + C completion`.
- **Locator-tier mix**: table of tier name → count across all cases, rendered as `| Tier | Count |`.
- **Mechanism firing rates**: table rendered as `| Mechanism | Cases with ≥1 firing |` with rows for `L1→L2 escalation`, `Replan`, and `Cache invalidation`, each showing `N/M` (non-skipped cases with at least one firing / total non-skipped).

"Ran" for the category summary SHALL be defined as cases whose `status` is NOT `"skipped"`. "Passed" for the category summary SHALL be cases whose `status` is `"succeeded"` or `"unverified"`.

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

#### Scenario: Category summary shows passing fixture suite with check mark

- **GIVEN** `tests/fixtures/score_categories_results.json` contains one `fixture-*` case with `status: "succeeded"`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the output SHALL contain a line matching `Fixture: 1/1 (100%) [target 80%] ✅`
- **AND** that line SHALL appear before the first `| fixture-` row of the per-case table

#### Scenario: Category summary shows failing drift suite with cross mark

- **GIVEN** `tests/fixtures/score_categories_results.json` contains one `drift-*` case with `status: "failed"`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the output SHALL contain a line matching `Drift suite: 0/1 (0%) [target 100%] ❌`

#### Scenario: Category summary shows skipped live suite with skip glyph

- **GIVEN** `tests/fixtures/score_categories_results.json` contains one `live-*` case with `status: "skipped"`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the output SHALL contain a line matching `Live: 0/0 ran [target 60%] ⏭️`

#### Scenario: Category summary appears before per-case table

- **GIVEN** `tests/fixtures/score_categories_results.json` with mixed suite cases
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the position of `Drift suite:` in the output string SHALL be less than the position of the first `|` character of the per-case table header row

## ADDED Requirements

### Requirement: Suite-threshold config block

`scripts/score.py` SHALL define a module-level constant `SUITE_THRESHOLDS: dict[str, dict]` that maps suite keys to their configuration. Each entry SHALL have:

- `name` (str): Human-readable display name for the suite.
- `id_prefixes` (list[str]): List of case-id prefix strings that belong to this suite. A case is assigned to a suite if its `id` starts with any prefix in the list. First matching suite wins (in `SUITE_THRESHOLDS` insertion order).
- `target_pct` (int): Minimum pass-rate percentage required to show ✅.

The constant SHALL include at minimum the following three suites:

| Key | `name` | `id_prefixes` | `target_pct` |
|---|---|---|---|
| `drift` | `"Drift suite"` | `["drift-", "maintenance-drift-", "correction-"]` | `100` |
| `fixture` | `"Fixture"` | `["fixture-"]` | `80` |
| `live` | `"Live"` | `["live-"]` | `60` |

No threshold value SHALL appear as a literal integer in the scoreboard-generation logic; all threshold comparisons SHALL reference `SUITE_THRESHOLDS`.

#### Scenario: SUITE_THRESHOLDS is importable and has the three required suites

- **GIVEN** `scripts/score.py` is imported
- **WHEN** `SUITE_THRESHOLDS` is accessed
- **THEN** it SHALL contain keys `"drift"`, `"fixture"`, and `"live"`
- **AND** `SUITE_THRESHOLDS["drift"]["target_pct"]` SHALL equal `100`
- **AND** `SUITE_THRESHOLDS["fixture"]["target_pct"]` SHALL equal `80`
- **AND** `SUITE_THRESHOLDS["live"]["target_pct"]` SHALL equal `60`

#### Scenario: drift suite id_prefixes includes correction- cases

- **GIVEN** `SUITE_THRESHOLDS["drift"]["id_prefixes"]` is inspected
- **WHEN** checking membership
- **THEN** `"correction-"` SHALL be in the list
- **AND** `"maintenance-drift-"` SHALL be in the list
