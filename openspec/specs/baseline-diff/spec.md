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
4. Emit aggregate delta lines: pass-rate delta (Δ%), total USD delta (ΔΔ$), p50 latency delta (Δms), p95 latency delta (Δms). Deltas SHALL be signed (e.g. `+3`, `-120`). The p50 and p95 latency deltas SHALL be computed over **only the cases whose `id` appears in both master and branch** (the intersection). If the intersection is empty, the latency delta cells SHALL render as `—` rather than a numeric value.
   - **Empty-side guard**: when `len(master["cases"]) == 0` OR `len(branch["cases"]) == 0`, the `Δ pass-rate`, `Δ total USD`, `Δ p50 latency`, and `Δ p95 latency` lines SHALL each emit `n/a (<reason>)` instead of a numeric delta, where `<reason>` is:
     - `master had 0 ran cases` if only the master side is empty.
     - `branch had 0 ran cases` if only the branch side is empty.
     - `both sides had 0 ran cases` if both sides are empty.
5. Prepend a header showing the `run_at` timestamps of both files.
6. Mark regression rows with `⚠️ REGRESSION` in the `Delta` column.
7. Mark improvement rows with `✅ IMPROVEMENT` in the `Delta` column.
8. After the latency rows, emit a "Cases" annotation line of the form `Cases: N common, +A added, -D dropped` where N is `|intersection|`, A is `|branch_only|`, and D is `|master_only|`.

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

- **GIVEN** `master` has two cases both `succeeded`, `usd=0.01` each, `latency_ms_total=1000` and `2000`, with ids `c1` and `c2`
- **AND** `branch` has the same two case ids `c1` and `c2`, both `succeeded`, `usd=0.02` each, `latency_ms_total=500` and `1500`
- **WHEN** `generate_diff_markdown(master, branch)` is called
- **THEN** the aggregate section SHALL contain `Δ pass-rate: +0%` (both succeeded in both)
- **AND** the aggregate section SHALL contain a positive USD delta reflecting the increase (e.g. `Δ total USD: +$0.0200`)
- **AND** the p50 delta SHALL be negative (latency improved, computed over the intersection of both case ids)
- **AND** the output SHALL contain `Cases: 2 common, +0 added, -0 dropped`

#### Scenario: When called with branch == master data, diff is empty of regressions

- **GIVEN** `master` and `branch` point to the same dict object (or structurally identical dicts)
- **WHEN** `generate_diff_markdown(master, branch)` is called
- **THEN** the output SHALL contain no `⚠️ REGRESSION` string
- **AND** all rows SHALL show `unchanged`

#### Scenario: Branch adds a new fast case but all common cases are unchanged

- **GIVEN** `master` has cases `a` (100 ms), `b` (200 ms), `c` (300 ms), all `succeeded`
- **AND** `branch` has the same three cases with identical statuses and latencies, plus a new case `d` at 50 ms
- **WHEN** `generate_diff_markdown(master, branch)` is called
- **THEN** `Δ p50 latency: +0ms` SHALL appear in the output (intersection of `{a,b,c}` shows no drift)
- **AND** `Δ p95 latency: +0ms` SHALL appear in the output
- **AND** the output SHALL contain `Cases: 3 common, +1 added, -0 dropped`

#### Scenario: No common cases between master and branch renders latency as dash

- **GIVEN** `master` has cases `a` and `b` only
- **AND** `branch` has cases `c` and `d` only (no overlap with master)
- **WHEN** `generate_diff_markdown(master, branch)` is called
- **THEN** the output SHALL contain `Δ p50 latency: —`
- **AND** the output SHALL contain `Δ p95 latency: —`
- **AND** the output SHALL contain `Cases: 0 common, +2 added, -2 dropped`

#### Scenario: Master with empty cases list paired with non-empty branch emits n/a

- **GIVEN** `master` has `cases: []` (zero cases)
- **AND** `branch` has one or more non-empty cases
- **WHEN** `generate_diff_markdown(master, branch)` is called
- **THEN** the output SHALL contain `Δ pass-rate: n/a (master had 0 ran cases)`
- **AND** the output SHALL contain `Δ total USD: n/a (master had 0 ran cases)`
- **AND** the output SHALL contain `Δ p50 latency: n/a (master had 0 ran cases)`
- **AND** the output SHALL contain `Δ p95 latency: n/a (master had 0 ran cases)`
- **AND** the output SHALL NOT contain `Δ pass-rate: +0%`

#### Scenario: Non-empty master paired with empty branch emits n/a

- **GIVEN** `master` has one or more non-empty cases
- **AND** `branch` has `cases: []` (zero cases)
- **WHEN** `generate_diff_markdown(master, branch)` is called
- **THEN** the output SHALL contain `Δ pass-rate: n/a (branch had 0 ran cases)`
- **AND** the output SHALL contain `Δ total USD: n/a (branch had 0 ran cases)`
- **AND** the output SHALL contain `Δ p50 latency: n/a (branch had 0 ran cases)`
- **AND** the output SHALL contain `Δ p95 latency: n/a (branch had 0 ran cases)`

#### Scenario: Both master and branch empty emits n/a with both-sides reason

- **GIVEN** both `master` and `branch` have `cases: []`
- **WHEN** `generate_diff_markdown(master, branch)` is called
- **THEN** the output SHALL contain `Δ pass-rate: n/a (both sides had 0 ran cases)`
- **AND** the output SHALL contain `Δ total USD: n/a (both sides had 0 ran cases)`
- **AND** the output SHALL contain `Δ p50 latency: n/a (both sides had 0 ran cases)`
- **AND** the output SHALL contain `Δ p95 latency: n/a (both sides had 0 ran cases)`

### Requirement: Latency delta population annotation is emitted after latency rows

After the `Δ p95 latency` line in the aggregate section, `generate_diff_markdown` SHALL emit exactly one line of the form:

- `Cases: N common, +A added, -D dropped`

where:
- `N` = number of case ids present in both master and branch (the intersection size)
- `A` = number of case ids present only in branch (added)
- `D` = number of case ids present only in master (dropped)

This line SHALL always be emitted (even when A == 0 and D == 0) so that reviewers have context for interpreting the intersection-based latency delta.

#### Scenario: Cases annotation reflects correct counts when branch adds cases

- **GIVEN** `master` has 3 cases and `branch` has 4 cases (3 common + 1 new)
- **WHEN** `generate_diff_markdown(master, branch)` is called
- **THEN** the output SHALL contain `Cases: 3 common, +1 added, -0 dropped`

#### Scenario: Cases annotation reflects correct counts when branch drops cases

- **GIVEN** `master` has 3 cases and `branch` has 2 cases (2 common + 1 dropped from master)
- **WHEN** `generate_diff_markdown(master, branch)` is called
- **THEN** the output SHALL contain `Cases: 2 common, +0 added, -1 dropped`

#### Scenario: Cases annotation shows all-zero deltas for identical run sets

- **GIVEN** `master` and `branch` have identical case id sets
- **WHEN** `generate_diff_markdown(master, branch)` is called
- **THEN** the output SHALL contain `Cases: N common, +0 added, -0 dropped` where N equals the number of cases

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

`.github/workflows/task2-benchmark.yml` SHALL contain a step named "Post diff as PR comment" with the following behaviour:

1. The step is conditional on `always() && github.event_name == 'pull_request'`.
2. The step reads `task2/benchmark/${{ github.head_ref }}/diff.md` (using the sanitized branch name).
3. If the file does not exist or is empty, the step exits 0 with a notice and skips posting.
4. Otherwise, the step detects any prior bot comment by calling `gh api "repos/$REPO/issues/$PR_NUMBER/comments"` with `--jq '.[] | select(.user.login == "github-actions[bot]") | .id'` and piping the result through `tail -1` to obtain the last bot comment id (or empty string if none exists). The detection call runs under `set -euo pipefail`; a non-zero exit from the detection call propagates immediately — the step MUST NOT fall through to the create path on detection failure.
5. When a prior bot comment id is found (non-empty detection result), the step updates it via `gh api --method PATCH "repos/$REPO/issues/comments/$COMMENT_ID"` passing the diff file content as the `body` field using `-F "body=@$DIFF_FILE"` (typed field, capital F) so that `@<filename>` reads file contents — `-f` would send the literal `@<filename>` string, not the file's contents.
6. When no prior bot comment exists (detection returned empty stdout, exit 0), the step creates a new comment via `gh pr comment "$PR_NUMBER" --body-file "$DIFF_FILE" --repo "$REPO"`.
7. The step MUST NOT use `--edit-last` with `2>/dev/null` — that pattern is replaced by the detection+update logic above.
8. The workflow `permissions:` block SHALL include both `pull-requests: write` and `issues: write`. The `issues: write` scope is required because GitHub's REST API routes PR comment updates through the Issues endpoint (`PATCH /repos/:owner/:repo/issues/comments/:id`), and `pull-requests: write` alone does not grant write access to that endpoint.

#### Scenario: CI detects prior bot comment and updates it via PATCH

- **GIVEN** a PR build where branch != master
- **AND** `task2/benchmark/<branch>/diff.md` exists and is non-empty
- **AND** `gh api .../issues/<n>/comments` filtered by `user.login == "github-actions[bot]"` returns a non-empty comment id
- **WHEN** the comment step runs
- **THEN** the step calls `gh api --method PATCH /repos/.../issues/comments/<id>` with the diff file content
- **AND** the step does NOT call `gh pr comment --edit-last`
- **AND** the step exits 0

#### Scenario: CI creates new comment when no prior bot comment exists

- **GIVEN** a PR build where branch != master
- **AND** `task2/benchmark/<branch>/diff.md` exists and is non-empty
- **AND** the detection call returns empty stdout (no prior bot comment), exit 0
- **WHEN** the comment step runs
- **THEN** the step calls `gh pr comment "$PR_NUMBER" --body-file "$DIFF_FILE" --repo "$REPO"` to create a fresh comment
- **AND** the step exits 0

#### Scenario: Detection call failure propagates — step does not silently fall through

- **GIVEN** a PR build where branch != master
- **AND** `task2/benchmark/<branch>/diff.md` exists and is non-empty
- **AND** the `gh api` detection call exits non-zero (e.g. auth error, network error, API 5xx)
- **WHEN** the comment step runs under `set -euo pipefail`
- **THEN** the step exits non-zero immediately after the detection call
- **AND** the step MUST NOT proceed to call `gh pr comment` or `gh api --method PATCH`

#### Scenario: CI skips comment when diff.md is absent

- **GIVEN** a PR build where `task2/benchmark/<branch>/diff.md` does NOT exist
- **WHEN** the comment step runs
- **THEN** the step exits 0 without calling any `gh` comment command

#### Scenario: CI skips comment on push to master (not a PR)

- **GIVEN** `github.event_name != 'pull_request'`
- **WHEN** the comment step is evaluated
- **THEN** the step is skipped entirely (conditional is false)

#### Scenario: YAML-shape test validates detection and update call presence

- **GIVEN** `.github/workflows/task2-benchmark.yml` has been edited with the idempotent comment logic
- **WHEN** `task2/tests/test_workflow_pr_comment.py` is run via `uv run pytest`
- **THEN** the test asserts the step's `run:` body contains `gh api` and `/comments`
- **AND** the test asserts the step's `run:` body contains `select(.user.login == "github-actions[bot]")` (the `--jq` filter)
- **AND** the test asserts the step's `run:` body contains `gh api --method PATCH`
- **AND** the test asserts the step's `run:` body contains `-F "body=@`
- **AND** the test asserts the step's `run:` body does NOT contain `--edit-last` or `2>/dev/null`
- **AND** the test asserts the workflow `permissions["issues"]` equals `"write"`
- **AND** the test passes (green)

### Requirement: workflow permissions include issues write for comment PATCH

The `permissions:` block at the top level of `.github/workflows/task2-benchmark.yml` SHALL include:

- `pull-requests: write` (already present; required for `gh pr comment`)
- `issues: write` (new; required for `gh api --method PATCH /repos/.../issues/comments/<id>`)

#### Scenario: permissions block contains both pull-requests and issues write

- **GIVEN** `.github/workflows/task2-benchmark.yml` is loaded via `yaml.safe_load`
- **WHEN** the `permissions` key is accessed
- **THEN** `permissions["pull-requests"]` equals `"write"`
- **AND** `permissions["issues"]` equals `"write"`
