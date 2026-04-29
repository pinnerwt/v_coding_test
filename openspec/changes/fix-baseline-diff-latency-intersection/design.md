## Context

`generate_diff_markdown` in `task2/scripts/baseline_diff.py` aggregates latency by collecting `latency_ms_total` from all master cases into one list and all branch cases into another, then taking the percentile of each and subtracting. This means that if branch has one new fast case (50 ms) while all common cases are unchanged at 100/200/300 ms, the branch p50 drops and the delta reports a latency improvement — even though no existing case changed. The population shift is a measurement artifact, not a real signal.

The fix is narrow: restrict the two latency lists to cases whose `id` appears in both runs. The per-case delta table and the pass-rate / USD aggregates are unaffected (pass-rate already operates on per-run totals, USD is a simple sum, and both intentionally include new/dropped cases).

## Goals / Non-Goals

**Goals:**

- Latency percentile delta reflects only common-case drift between master and branch.
- Empty-intersection case (no common cases at all) renders a safe sentinel (`—`) rather than `+0ms` or an exception.
- Reviewers can see at a glance how many cases are common vs. added vs. dropped via a "Cases:" annotation line below the latency rows.
- All existing and new tests pass; no existing test is silently weakened.

**Non-Goals:**

- Emitting dual numbers (intersection + whole-population) — option (c) from the ticket — is explicitly out of scope.
- Modifying pass-rate or USD aggregation semantics.
- Changing the per-case delta table (new/dropped rows stay, classification logic unchanged).
- Adding any new external dependency.

## Decisions

### Decision 1: Intersection-only latency aggregation

**Chosen:** Filter both latency lists to `case_id ∈ set(master_ids) & set(branch_ids)` before computing percentiles.

**Alternatives considered:**
- *Whole-population with documentation caveat (option b)*: Documents the artifact rather than fixing it. Reviewers still see misleading numbers; trust is not restored.
- *Dual emission (option c)*: Doubles the noise in `diff.md` and requires readers to understand two semantics simultaneously.

**Rationale:** The sole purpose of latency delta reporting is to surface per-case regression. Intersection semantics is the only design that makes the number mean what the label says.

### Decision 2: Empty-intersection renders `—`

**Chosen:** When `set(master_ids) & set(branch_ids)` is empty, emit `Δ p50 latency: —` and `Δ p95 latency: —`.

**Rationale:** `_percentile([], pct)` currently returns `0`, which would produce a spurious `+0ms`. Returning `—` is already the rendering convention for absent data in the per-case table (e.g. `ms or '—'`). The "Cases: 0 common, +A added, -D dropped" annotation provides the explanation.

### Decision 3: "Cases: N common, +A added, -D dropped" annotation

**Chosen:** Add one annotation line below the latency rows whenever the function runs (not conditionally on mismatch), because the main spec's `diff.md` schema has no existing mechanism to surface added/dropped case counts in the aggregate section. The per-case table shows which cases are new/dropped, but the aggregate section had no summary count.

**Rationale:** Without the annotation, reviewers seeing `Δ p50 latency: +0ms` when branch added 10 new fast cases have no way to know the intersection is a subset of the full run. The one-liner gives full context.

## Risks / Trade-offs

- **Existing test `test_aggregate_latency_delta_negative`** uses a synthetic where both cases are common (same ids in master and branch), so intersection == whole-population; that test continues to pass unchanged. Spot-check before closing.
- **`test_aggregate_latency_delta_negative` assumes whole-population semantics** for a two-case set where the case ids match — no change needed, the math is identical.
- [Risk] A future caller passes a results dict where `id` fields are missing → `case_id` lookup returns `None` keys and intersection logic silently excludes cases. Mitigation: the existing code already relies on `c["id"]` being present for the per-case table; this is no worse.

## Migration Plan

1. Add failing test (`red`) in `test_baseline_diff.py`.
2. Modify `generate_diff_markdown` to compute intersection latency lists (`green`).
3. Add "Cases: N common, +A added, -D dropped" annotation line and its test.
4. Add empty-intersection test.
5. Review and update any existing tests whose latency assertions now need adjustment.
6. Run `uv run ruff check .` and `uv run pytest` — both must be clean.

No deployment steps needed; `baseline_diff.py` is a library module called from `benchmark.py` and CI.

## Open Questions

_(none — all decisions made per the orchestrator's directive to use option (a))_
