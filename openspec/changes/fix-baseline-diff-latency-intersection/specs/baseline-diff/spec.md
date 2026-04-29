## MODIFIED Requirements

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

## ADDED Requirements

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
