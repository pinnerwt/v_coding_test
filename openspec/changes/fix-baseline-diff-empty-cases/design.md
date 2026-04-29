## Context

`task2/scripts/baseline_diff.py::generate_diff_markdown` computes aggregate deltas after building the per-case table. The pass-rate computation is:

- `m_ran = len(m_list)` — counts all cases in master, including `skipped`.
- `m_pct = int(100 * _pass_count(m_list) / m_ran) if m_ran else 0` — when `m_ran == 0`, returns `0` silently.

The same pattern applies to `b_ran` / `b_pct`. The USD and latency deltas over an all-skipped or empty branch compute as `+$0.0000` and `+0ms` respectively because `sum(...)` and `_percentile([], ...)` default to zero. A PR reviewer reading the aggregate block has no way to distinguish "genuinely no regression" from "no data was collected."

The relevant symbols:
- `_pass_count(cases)` in `task2/scripts/baseline_diff.py` — returns count of cases whose `status` is in `PASS_STATUSES`; does not filter skipped from total.
- `generate_diff_markdown(master, branch)` in `task2/scripts/baseline_diff.py` — builds the full diff markdown; contains the aggregate block that must be changed.
- `m_ran` / `b_ran` — local variables counting total cases on each side; zero when `cases: []` or when all cases are absent.

## Goals / Non-Goals

**Goals:**

- Emit `n/a (<reason>)` for `Δ pass-rate`, `Δ total USD`, `Δ p50 latency`, and `Δ p95 latency` when either side has zero runnable cases (`m_ran == 0` or `b_ran == 0`).
- Make the reason string specific enough for a reviewer to act on: e.g. `n/a (master had 0 ran cases)` or `n/a (branch had 0 ran cases)`.
- Preserve all existing behavior for the normal case (both sides non-empty).
- Add failing tests first (TDD red step) before changing production code.

**Non-Goals:**

- Filtering `skipped` cases out of `m_ran` / `b_ran` (ticket scopes to `cases: []` / all-absent, not all-skipped; that is a separate concern).
- Changing the per-case delta table format (rows are unaffected).
- Adding a new CLI flag or new CaseResult field.
- Modifying `benchmark.py`, `score.py`, `eval.py`, or `trends.py`.

## Decisions

### Decision 1: Option (a) — emit `n/a (<reason>)` instead of `+0%`

Pre-resolved by orchestrator. The three options were:

- **(a)** Emit `n/a (master had 0 ran cases)` (and similarly for USD/latency) when a side has no runnable cases.
- **(b)** Keep `+0%` and add a one-line note above the aggregate block.
- **(c)** Suppress the aggregate block entirely.

Option (a) chosen because it is the most informative signal with no ambiguity. Option (b) leaves the misleading `+0%` in the headline. Option (c) would lose master-side count visibility entirely.

**Alternative considered**: Option (b) — add a banner line. Rejected because the `+0%` headline number is still present and can be read in isolation by automated tooling or a distracted reviewer.

### Decision 2: Guard on `m_ran == 0 or b_ran == 0` as a single condition

When either side is empty, all four aggregate metrics are unreliable (pass-rate requires both denominators; USD delta is vacuously zero; latency delta is vacuously zero). A single guard covering all four lines is cleaner than per-metric guards. The reason string identifies which side triggered the guard.

### Decision 3: Reason string format

Use `master had 0 ran cases` / `branch had 0 ran cases` / `both sides had 0 ran cases` depending on which sides are empty. Keeps it short and machine-parseable for any future tooling.

## Risks / Trade-offs

- **Existing test `test_no_op_branch_pass_rate_delta_zero` asserts `Δ pass-rate: +0%`** — this test uses the non-empty master fixture, so it is unaffected. No existing test uses `cases: []`.
- **String format coupling** — tests will assert exact strings like `n/a (master had 0 ran cases)`; if the wording changes later, tests break. This is acceptable: the format is the spec.

## Open Questions

None — option (a) and reason string format are pre-resolved by orchestrator.
