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
4. Emit aggregate delta lines: pass-rate delta (Δ%), total USD delta (Δ$), p50 latency delta (Δms), p95 latency delta (Δms). Deltas SHALL be signed (e.g. `+3`, `-120`). The p50 and p95 latency deltas SHALL be computed over **only the cases whose `id` appears in both master and branch** (the intersection). If the intersection is empty, the latency delta cells SHALL render as `—` rather than a numeric value.
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
