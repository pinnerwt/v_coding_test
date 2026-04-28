## MODIFIED Requirements

### Requirement: score.py reads a results JSON and emits a markdown scoreboard

`scripts/score.py` SHALL be a standalone script (invocable via `uv run python -m scripts.score` or `uv run python scripts/score.py`) that:

1. Accepts a positional `results_file` argument (path to `eval/results/<ts>.json`). When omitted, it SHALL default to the most-recently modified file in `eval/results/`.
2. Reads and validates the results JSON.
3. Emits a markdown scoreboard to stdout (or to a file via `--output`).

The scoreboard SHALL contain all of the following sections, in order:

- **Category summary**: one line per suite in `SUITE_THRESHOLDS` insertion order, rendered BEFORE the per-case table. Each line SHALL follow the format: `<SuiteName>: <passed>/<ran> (<pct>%) [target <target>%] <glyph>` where `<glyph>` is ✅ when passed/ran >= target_pct and ran > 0, ❌ when passed/ran < target_pct and ran > 0, or ⏭️ when ran == 0. Cases not matching any suite prefix SHALL be omitted from the category summary (not shown as "other" row).
- **Per-case status table**: columns `Case`, `Status`, `Steps`, `Latency (ms)`, `USD`, `Tokens (P+C)`, `Escalations`, `Replans`, `Cache Inv.`, `Failure class`
- **Summary line**: `N/M succeeded (X%)` where N = passed (succeeded + unverified), M = total non-skipped.
- **Latency percentiles**: `p50: Xms  p95: Xms` computed over `latency_ms_total` values of non-skipped cases.
- **Totals**: `Total USD: $X.XXXX   Total tokens: P prompt + C completion`.
- **Locator-tier mix**: table of tier name → count across all cases, rendered as `| Tier | Count |`.
- **Mechanism firing rates**: table rendered as `| Mechanism | Cases with ≥1 firing |` with rows for `L1→L2 escalation`, `Replan`, and `Cache invalidation`, each showing `N/M` (non-skipped cases with at least one firing / total non-skipped).

"Ran" for the category summary SHALL be defined as cases whose `status` is NOT `"skipped"`. "Passed" for the category summary SHALL be cases whose `status` is `"succeeded"` or `"unverified"`.

**Per-case Status column rendering (added by implement-bench-repeats):**

`generate_scoreboard` SHALL include a helper `_render_case_status(case: dict) -> str` that determines what to display in the `Status` column of the per-case table:

- If `case.get("repeats", 1) > 1`: render `{passed_runs}/{repeats} ✓` when `passed_runs == repeats`, else `{passed_runs}/{repeats} ✗`.
- Otherwise (repeats absent or `1`): render `case["status"]` as a plain string (preserving existing behavior).

The helper SHALL be backward-compatible: results JSON files that do not contain `repeats` or `passed_runs` keys SHALL render using the existing plain-`status` path without raising exceptions.

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

#### Scenario: Per-case Status column shows fractional rate when repeats > 1 and all pass

- **GIVEN** a results file with one case entry containing `repeats=3`, `passed_runs=3`, `status="succeeded"`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the per-case table row for that case SHALL contain `3/3 ✓` in the Status column

#### Scenario: Per-case Status column shows fractional rate when repeats > 1 and partial pass

- **GIVEN** a results file with one case entry containing `repeats=3`, `passed_runs=2`, `status="failed"`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the per-case table row for that case SHALL contain `2/3 ✗` in the Status column

#### Scenario: Per-case Status column renders plain status when repeats == 1 or absent

- **GIVEN** a results file with case entries that have no `repeats` key
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the per-case table row SHALL render the `status` field as a plain string (e.g. `succeeded`, `failed`)
- **AND** no exception SHALL be raised

#### Scenario: _render_case_status is backward-compatible with missing passed_runs

- **GIVEN** a case dict with `repeats=3` but no `passed_runs` key
- **WHEN** `_render_case_status(case)` is called
- **THEN** it SHALL NOT raise a `KeyError`
- **AND** SHALL return a string (defaulting to plain status or `0/3 ✗`)
