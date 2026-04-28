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

### Requirement: Skipped subsection with reason counts
`generate_scoreboard()` SHALL append a "Skipped" subsection to the scoreboard output when at least one case has `status="skipped"`. The subsection SHALL appear after the per-case table rows (and the blank line following them) but before the aggregate summary line.

The subsection SHALL render as:

```
**Skipped** (<total_skipped> cases)

| Skip reason | Count |
|---|---|
| live_disabled | <N> |
| fixture_missing | <N> |
```

- Only reasons that appear in the results (count ≥ 1) SHALL be included as rows.
- Reasons SHALL be listed in the following canonical order: `live_disabled`, `infra_unavailable`, `fixture_missing`, `feature_not_implemented`. Reasons not present in results are omitted entirely.
- `skip_reason` values that are `None` (e.g. from old result files lacking the field) SHALL be treated as if the case was not skipped for counting purposes — they SHALL NOT appear as a `None` row.
- When no cases are skipped, the "Skipped" subsection SHALL be omitted entirely.

#### Scenario: Skipped subsection appears when skip_reason is present
- **GIVEN** a results file with one case having `status="skipped"` and `skip_reason="live_disabled"`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the output SHALL contain a line matching `**Skipped** (1 cases)`
- **AND** the output SHALL contain a row `| live_disabled | 1 |`

#### Scenario: Multiple skip reasons are each counted separately
- **GIVEN** a results file with two skipped cases: one `live_disabled` and one `fixture_missing`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the output SHALL contain `| live_disabled | 1 |` and `| fixture_missing | 1 |`
- **AND** the header line SHALL read `**Skipped** (2 cases)`

#### Scenario: No skipped cases omits the subsection entirely
- **GIVEN** a results file with no cases having `status="skipped"`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the output SHALL NOT contain the string `**Skipped**`

#### Scenario: Skipped subsection appears before aggregate summary line
- **GIVEN** a results file with at least one skipped case
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the position of `**Skipped**` in the output string SHALL be less than the position of the aggregate summary line (the `**N/M succeeded` line)

#### Scenario: Old result files without skip_reason field produce no Skipped subsection
- **GIVEN** a results file whose case entries have no `skip_reason` key
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** no `**Skipped**` section SHALL appear and no exception SHALL be raised
