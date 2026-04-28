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
- **Failure histogram**: a `**Failure histogram**` block listing `failure_class → count` for all failed cases with a non-None `failure_class`, sorted descending by count (ties alphabetical). Suppressed entirely when there are no failed cases with a classifiable `failure_class`. Rendered AFTER the category summary and BEFORE the per-case status table.
- **Per-case status table**: columns `Case`, `Status`, `Steps`, `Latency (ms)`, `USD`, `Tokens (P+C)`, `Escalations`, `Replans`, `Cache Hits`, `Cache Misses`, `Cache Inv.`, `Failure class`
- **Summary line**: `N/M succeeded (X%)` where N = passed (succeeded + unverified), M = total non-skipped.
- **Latency percentiles**: `p50: Xms  p95: Xms` computed over `latency_ms_total` values of non-skipped cases.
- **Totals**: `Total USD: $X.XXXX   Total tokens: P prompt + C completion`.
- **Locator-tier mix**: table of tier name → count across all cases, rendered as `| Tier | Count |`.
- **Mechanism firing rates**: table rendered as `| Mechanism | Cases with ≥1 firing |` with rows for `L1→L2 escalation`, `Replan`, and `Cache invalidation`, each showing `N/M` (non-skipped cases with at least one firing / total non-skipped).

"Ran" for the category summary SHALL be defined as cases whose `status` is NOT `"skipped"`. "Passed" for the category summary SHALL be cases whose `status` is `"succeeded"` or `"unverified"`.

**Per-case cache columns:**

The per-case table SHALL include three cache columns in the following left-to-right order, adjacent to each other and immediately left of `Failure class`:

- `Cache Hits` — populated from `case.get("cache_events", {}).get("hits", 0)`
- `Cache Misses` — populated from `case.get("cache_events", {}).get("misses", 0)`
- `Cache Inv.` — populated from `case.get("cache_events", {}).get("invalidations", 0)` (existing column, unchanged)

All three columns SHALL default to `0` when `cache_events` is absent or the key is missing (backward-compatible with old result files).

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

#### Scenario: Failure histogram appears after category summary and before per-case table

- **GIVEN** a results file with at least one failed case that has a non-None `failure_class`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the position of `**Failure histogram**` in the output SHALL be greater than the position of the category summary block
- **AND** the position of `**Failure histogram**` SHALL be less than the position of the per-case table header row (the `| Case |` header)

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

#### Scenario: Cache Hits and Cache Misses columns appear in per-case table header

- **GIVEN** a results file with at least one case entry
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the per-case table header row SHALL contain `Cache Hits`
- **AND** the per-case table header row SHALL contain `Cache Misses`
- **AND** both columns SHALL appear to the left of `Cache Inv.` in the header

#### Scenario: Cache Hits and Cache Misses populated from cache_events dict

- **GIVEN** a results file with a case containing `cache_events: {hits: 1, misses: 1, invalidations: 0}`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the per-case table row for that case SHALL contain `1` in the `Cache Hits` column
- **AND** the per-case table row for that case SHALL contain `1` in the `Cache Misses` column
- **AND** the per-case table row for that case SHALL contain `0` in the `Cache Inv.` column

#### Scenario: Cache Hits and Cache Misses default to 0 when cache_events is absent

- **GIVEN** a results file with a case that has no `cache_events` key
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the per-case table row SHALL show `0` for both `Cache Hits` and `Cache Misses`
- **AND** no exception SHALL be raised

### Requirement: Failure histogram block

`generate_scoreboard(data)` SHALL emit a failure-histogram subsection after the category summary block and before the per-case table header row. The subsection SHALL render as:

- A header line: `**Failure histogram** (N failed)` where N is the count of non-skipped cases whose `status` is `"failed"`, `"blocked"`, or `"timeout"`.
- A blank line.
- A two-column markdown table with header `| Failure class | Count |` and separator row `|---|---|`.
- One row per distinct non-None `failure_class` value, sorted descending by count; ties broken alphabetically by class name.
- Only classes with count >= 1 SHALL appear as rows.

The block SHALL be suppressed entirely (no header, no table) when there are no failed cases or when the total count across all class rows is zero (i.e., all failed cases have `failure_class=None`).

Cases with `failure_class=None` SHALL NOT appear as a `None` row in the histogram.

`generate_scoreboard` SHALL NOT require any new parameters; it reads `failure_class` from each case dict using `case.get("failure_class")`.

#### Scenario: Histogram block appears when at least one failed case has a non-None failure_class

- **GIVEN** a results file with one failed case having `failure_class="supervisor_halt"`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the output SHALL contain `**Failure histogram**`
- **AND** the output SHALL contain `| Failure class | Count |`
- **AND** the output SHALL contain a row `| supervisor_halt | 1 |`

#### Scenario: Histogram counts are correct with multiple classes

- **GIVEN** a results file with five failed cases: three with `failure_class="supervisor_halt"`, one with `failure_class="locator_miss"`, one with `failure_class="tool_error"`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the output SHALL contain `| supervisor_halt | 3 |`
- **AND** the output SHALL contain `| locator_miss | 1 |`
- **AND** the output SHALL contain `| tool_error | 1 |`
- **AND** `supervisor_halt` SHALL appear before `locator_miss` and `tool_error` in the output (higher count first)

#### Scenario: Histogram sorts ties alphabetically

- **GIVEN** a results file with two failed cases: one `failure_class="tool_error"` and one `failure_class="locator_miss"` (both count=1)
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** `locator_miss` SHALL appear before `tool_error` in the histogram table (alphabetical order for tied counts)

#### Scenario: Histogram block is omitted when no cases are failed

- **GIVEN** a results file where all cases have `status="succeeded"` or `status="skipped"`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the output SHALL NOT contain `**Failure histogram**`

#### Scenario: Histogram block is omitted when all failed cases have failure_class=None

- **GIVEN** a results file with one failed case having `failure_class=null` (None)
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the output SHALL NOT contain `**Failure histogram**`
- **AND** no exception SHALL be raised

#### Scenario: Histogram is backward-compatible with results lacking failure_class key

- **GIVEN** a results file whose case dicts have no `failure_class` key
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the histogram block SHALL be omitted
- **AND** no exception SHALL be raised

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

### Requirement: score.py --detail flag emits per-step breakdown table inline for failing cases

`scripts/score.py` SHALL accept an optional `--detail` boolean flag (default `False`). When `--detail` is passed:

- For each case in the scoreboard whose status is NOT `"succeeded"`, `"unverified"`, or `"skipped"` (i.e. failing cases), `generate_scoreboard` SHALL emit a per-step markdown table immediately after that case's row in the per-case table. The table SHALL NOT be emitted for passing or skipped cases.
- The table SHALL have the following columns (in order): `Step`, `Tool`, `Prompt Tokens`, `Completion Tokens`, `Latency (ms)`.
- Each row in the table SHALL correspond to one entry in `case["step_breakdown"]`, in the order returned by the results JSON (`step_breakdown[0]` → row 1, etc.).
- The `Tool` column SHALL be populated by joining `step["tool_calls"]` with `", "` (comma-space). When `tool_calls` is empty, the cell SHALL contain `"-"`.
- When `step_breakdown` is absent, `None`, or an empty list for a failing case, no table SHALL be emitted for that case (silent no-op).
- When `--detail` is passed, the inline table SHALL replace the collapsible `<details>` block for that case (only one form is emitted per case, not both).
- `generate_scoreboard` SHALL accept an optional `detail: bool = False` keyword argument so callers can pass it programmatically without going through `main()`.

#### Scenario: --detail flag produces per-step table for failing case

- **GIVEN** a results file with one failing case (`status="failed"`) whose `step_breakdown` has two entries: `[{"step": 1, "tool_calls": ["goto"], "prompt_tokens": 120, "completion_tokens": 15, "latency_ms": 800}, {"step": 2, "tool_calls": ["done"], "prompt_tokens": 200, "completion_tokens": 30, "latency_ms": 1200}]`
- **WHEN** `generate_scoreboard(data, detail=True)` is called
- **THEN** the output SHALL contain a markdown table with header `| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |`
- **AND** the output SHALL contain a row matching `| 1 | goto | 120 | 15 | 800 |`
- **AND** the output SHALL contain a row matching `| 2 | done | 200 | 30 | 1200 |`

#### Scenario: --detail flag produces no table for passing case

- **GIVEN** a results file with one passing case (`status="succeeded"`) whose `step_breakdown` is non-empty
- **WHEN** `generate_scoreboard(data, detail=True)` is called
- **THEN** the output SHALL NOT contain the string `Prompt Tokens` in the context of a per-step table for that passing case

#### Scenario: --detail flag produces no table when step_breakdown is empty

- **GIVEN** a results file with one failing case (`status="failed"`) whose `step_breakdown` is `[]` (empty list)
- **WHEN** `generate_scoreboard(data, detail=True)` is called
- **THEN** no per-step table header (`Step | Tool | Prompt Tokens`) SHALL appear in the output

#### Scenario: --detail flag is forwarded from main() to generate_scoreboard

- **GIVEN** `score.py` is invoked as `score.py <results_file> --detail`
- **WHEN** `main()` parses the argument
- **THEN** `generate_scoreboard` SHALL be called with `detail=True`

#### Scenario: tool_calls list is comma-joined in the Tool column

- **GIVEN** a failing case whose `step_breakdown` has one entry with `tool_calls: ["click", "read"]`
- **WHEN** `generate_scoreboard(data, detail=True)` is called
- **THEN** the Tool column cell for that step SHALL contain `click, read`

#### Scenario: empty tool_calls list renders as dash in the Tool column

- **GIVEN** a failing case whose `step_breakdown` has one entry with `tool_calls: []`
- **WHEN** `generate_scoreboard(data, detail=True)` is called
- **THEN** the Tool column cell for that step SHALL contain `-`

### Requirement: score.py emits collapsible step breakdown block for failing cases in default mode

When `--detail` is NOT passed (the default), `generate_scoreboard` SHALL emit a collapsible `<details>` block immediately after each failing case's per-case table row when that case has a non-empty `step_breakdown`. The block SHALL:

- Open with `<details><summary>step breakdown (N steps)</summary>` where `N` is `len(step_breakdown)`.
- Contain the same per-step markdown table (columns `Step`, `Tool`, `Prompt Tokens`, `Completion Tokens`, `Latency (ms)`) as the `--detail` inline form.
- Close with `</details>`.
- Be omitted entirely when `step_breakdown` is absent, `None`, or empty.
- Be omitted for passing (`succeeded`, `unverified`) and skipped cases regardless of `step_breakdown` content.
- NOT be emitted when `--detail` is active (inline table takes precedence).

The `_render_step_breakdown(steps: list[dict]) -> str` helper SHALL be defined in `scripts/score.py` and return the markdown table string (header + rows) for the given list of step dicts. It SHALL return an empty string when `steps` is empty. Callers are responsible for wrapping the result in `<details>` or emitting it inline.

#### Scenario: default mode emits collapsible block for failing case with step_breakdown

- **GIVEN** a results file with one failing case (`status="failed"`) whose `step_breakdown` has three entries
- **WHEN** `generate_scoreboard(data)` is called without `detail=True`
- **THEN** the output SHALL contain `<details><summary>step breakdown (3 steps)</summary>`
- **AND** the output SHALL contain `</details>`
- **AND** the output SHALL contain a markdown table with `| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |` inside the block

#### Scenario: default mode does not emit block for passing case

- **GIVEN** a results file with one passing case (`status="succeeded"`) whose `step_breakdown` is non-empty
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the output SHALL NOT contain `<details>` related to a step breakdown for that passing case

#### Scenario: default mode does not emit block when step_breakdown is absent

- **GIVEN** a results file with one failing case whose dict has no `step_breakdown` key
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** no `<details>` block SHALL appear in the output
- **AND** no exception SHALL be raised

#### Scenario: _render_step_breakdown returns empty string for empty list

- **GIVEN** `_render_step_breakdown([])` is called
- **WHEN** the function returns
- **THEN** the result SHALL be an empty string `""`

#### Scenario: _render_step_breakdown returns table for non-empty list

- **GIVEN** `_render_step_breakdown([{"step": 1, "tool_calls": ["goto"], "prompt_tokens": 100, "completion_tokens": 10, "latency_ms": 500}])` is called
- **WHEN** the function returns
- **THEN** the result SHALL contain the header `| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |`
- **AND** the result SHALL contain a row with `1`, `goto`, `100`, `10`, `500`

#### Scenario: collapsible block is not emitted when --detail is active

- **GIVEN** a results file with one failing case with a non-empty `step_breakdown`
- **WHEN** `generate_scoreboard(data, detail=True)` is called
- **THEN** the output SHALL NOT contain `<details>` for that case's step breakdown
- **AND** the inline table SHALL be present instead
