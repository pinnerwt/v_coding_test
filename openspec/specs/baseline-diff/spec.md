# baseline-diff Specification

## Purpose
TBD - created by archiving change implement-scoreboard-baseline-diff. Update Purpose after archive.

## Requirements

### Requirement: generate_diff_markdown produces a Δ vs master table

`task2/scripts/baseline_diff.py` SHALL expose a public function:

```python
def generate_diff_markdown(master: dict, branch: dict) -> str:
```

where `master` and `branch` are parsed `results.json` dicts (keys: `run_at`, `cases`). The function SHALL:

1. Match cases by `id` across both dicts.
2. For each case present in either file, classify the per-case delta as one of:
   - `regression` — was `succeeded` or `unverified` in master, now `failed` or `skipped` in branch.
   - `improvement` — was `failed` or `skipped` in master, now `succeeded` or `unverified` in branch.
   - `unchanged` — same pass/fail outcome in both files.
   - `new` — present only in branch (no master entry).
   - `dropped` — present only in master (no branch entry).
3. Emit a per-case delta table with columns: `Case`, `Master status`, `Branch status`, `Delta`.
4. Emit aggregate delta lines: pass-rate delta (Δ%), total USD delta (ΔΔ$), p50 latency delta (Δms), p95 latency delta (Δms). Deltas SHALL be signed (e.g. `+3`, `-120`).
5. Prepend a header showing the `run_at` timestamps of both files.
6. Mark regression rows with `⚠️ REGRESSION` in the `Delta` column.
7. Mark improvement rows with `✅ IMPROVEMENT` in the `Delta` column.

The function SHALL be pure: no file I/O, no subprocess calls. All inputs and outputs are Python values / strings.

#### Scenario: Synthetic master+branch pair produces expected diff markdown

- **GIVEN** `master` has one case `fixture-a` with `status="succeeded"` and one case `fixture-b` with `status="failed"`
- **AND** `branch` has `fixture-a` with `status="failed"`, `fixture-b` with `status="succeeded"`, and `fixture-c` with `status="succeeded"`
- **WHEN** `generate_diff_markdown(master, branch)` is called
- **THEN** the output SHALL contain a row for `fixture-a` with `⚠️ REGRESSION` in the Delta column
- **AND** the output SHALL contain a row for `fixture-b` with `✅ IMPROVEMENT` in the Delta column
- **AND** the output SHALL contain a row for `fixture-c` with `new` classification in the Delta column

#### Scenario: No-op branch (identical to master) produces empty Δ table

- **GIVEN** `master` and `branch` have identical `cases` lists (same ids, same statuses)
- **WHEN** `generate_diff_markdown(master, branch)` is called
- **THEN** the output SHALL contain no `REGRESSION` or `IMPROVEMENT` markers
- **AND** all rows in the per-case delta table SHALL show `unchanged` in the Delta column
- **AND** the aggregate pass-rate delta SHALL be `Δ pass-rate: +0%`

#### Scenario: Previously-passing case now failing is marked as regression

- **GIVEN** `master` has one case with `status="succeeded"`
- **AND** `branch` has the same case id with `status="failed"`
- **WHEN** `generate_diff_markdown(master, branch)` is called
- **THEN** the output SHALL contain the string `⚠️ REGRESSION`
- **AND** the per-case row for that case SHALL show `⚠️ REGRESSION` in the Delta column

#### Scenario: Aggregate deltas are computed correctly

- **GIVEN** `master` has two cases both `succeeded`, `usd=0.01` each, `latency_ms_total=1000` and `2000`
- **AND** `branch` has the same two cases both `succeeded`, `usd=0.02` each, `latency_ms_total=500` and `1500`
- **WHEN** `generate_diff_markdown(master, branch)` is called
- **THEN** the aggregate section SHALL contain `Δ pass-rate: +0%` (both succeeded in both)
- **AND** the aggregate section SHALL contain a positive USD delta reflecting the increase (e.g. `Δ total USD: +$0.0200`)
- **AND** the p50 delta SHALL be negative (latency improved)

#### Scenario: When called with branch == master data, diff is empty of regressions

- **GIVEN** `master` and `branch` point to the same dict object (or structurally identical dicts)
- **WHEN** `generate_diff_markdown(master, branch)` is called
- **THEN** the output SHALL contain no `⚠️ REGRESSION` string
- **AND** all rows SHALL show `unchanged`

### Requirement: benchmark.py writes diff.md when branch ≠ master and baseline exists

`task2/scripts/benchmark.py` SHALL, after calling `write_outputs`, call a `write_diff` helper that:

1. Checks if the resolved branch name equals `"master"` (after sanitization). If so, skips writing `diff.md`.
2. Checks if `task2/benchmark/master/results.json` exists. If not, skips writing `diff.md`.
3. Otherwise, loads `task2/benchmark/master/results.json`, calls `generate_diff_markdown(master_data, branch_data)`, and writes the result to `task2/benchmark/<sanitized-branch>/diff.md`.

No exception SHALL be raised when the baseline file is missing; the absence is logged to stderr at INFO level and the run continues.

#### Scenario: Non-master branch with existing master baseline writes diff.md

- **GIVEN** branch is `"my-feature"` (≠ master)
- **AND** `task2/benchmark/master/results.json` exists with valid content
- **AND** the benchmark run completes and writes `task2/benchmark/my-feature/results.json`
- **WHEN** `write_diff` runs
- **THEN** `task2/benchmark/my-feature/diff.md` SHALL be written
- **AND** its content SHALL be the output of `generate_diff_markdown(master_data, branch_data)`

#### Scenario: Master branch run does not write diff.md

- **GIVEN** branch is `"master"`
- **WHEN** `write_diff` runs
- **THEN** `task2/benchmark/master/diff.md` SHALL NOT be written

#### Scenario: Non-master branch with missing master baseline skips diff.md gracefully

- **GIVEN** branch is `"my-feature"`
- **AND** `task2/benchmark/master/results.json` does NOT exist
- **WHEN** `write_diff` runs
- **THEN** `task2/benchmark/my-feature/diff.md` SHALL NOT be written
- **AND** no exception SHALL be raised
- **AND** a message SHALL be written to stderr indicating the baseline is absent

### Requirement: CI workflow posts diff.md as a PR comment

`.github/workflows/task2-benchmark.yml` SHALL add a step after the existing `Verify benchmark recorded for branch` step with the following behaviour:

1. The step is conditional on `github.event_name == 'pull_request'`.
2. The step reads `task2/benchmark/${{ github.head_ref }}/diff.md` (using the sanitized branch name).
3. If the file does not exist or is empty, the step exits 0 with a notice and skips posting.
4. Otherwise, it posts the file content as a PR comment using `gh pr comment`.
5. On re-runs, the step SHALL update the existing bot comment (`--edit-last`) rather than creating a new one. If no prior comment exists, it SHALL create a new one.
6. The step requires `pull-requests: write` permission.

#### Scenario: CI posts diff comment on PR run when diff.md exists

- **GIVEN** a PR build where branch ≠ master
- **AND** `task2/benchmark/<branch>/diff.md` exists in the checkout
- **WHEN** the comment step runs
- **THEN** `gh pr comment` is called with the diff file content
- **AND** the step exits 0

#### Scenario: CI skips comment when diff.md is absent

- **GIVEN** a PR build where `task2/benchmark/<branch>/diff.md` does NOT exist
- **WHEN** the comment step runs
- **THEN** the step exits 0 without calling `gh pr comment`

#### Scenario: CI skips comment on push to master (not a PR)

- **GIVEN** `github.event_name != 'pull_request'`
- **WHEN** the comment step is evaluated
- **THEN** the step is skipped entirely (conditional is false)
