## Why

`generate_diff_markdown` computes `Δ p50` / `Δ p95` latency over the whole per-run case population, so when branch adds or drops even one case the delta can flip sign for purely population-shift reasons — not because any common case got faster or slower. This undermines reviewer trust in the auto-diff feature, whose entire purpose is to surface real regressions.

## What Changes

- The latency percentile aggregation in `task2/scripts/baseline_diff.py::generate_diff_markdown` is restricted to cases whose `id` appears in **both** master and branch (intersection semantics).
- When the intersection is empty, the latency delta cells render as `—` (undefined) rather than a misleading `+0ms` or a crash.
- A "Cases: N common, +A added, -D dropped" annotation line is added under the latency rows in `diff.md` so reviewers can see at a glance why the intersection population might be smaller than the full case table.
- Existing tests whose latency assertions implicitly assumed whole-population semantics are updated to match the new intersection semantics or renamed to make their assumption explicit.

## Capabilities

### New Capabilities

_(none)_

### Modified Capabilities

- `baseline-diff`: The requirement governing aggregate latency delta output now mandates intersection-only population semantics for `Δ p50 latency` and `Δ p95 latency`, plus a new "Cases" annotation line under the latency metrics.

## Impact

- **`task2/scripts/baseline_diff.py`** — `generate_diff_markdown` function (latency aggregation logic, ~lines 84-91).
- **`task2/tests/test_baseline_diff.py`** — existing `test_aggregate_latency_delta_negative` and any other tests that assert specific latency delta values; new intersection and empty-intersection tests added.
- **`openspec/specs/baseline-diff/spec.md`** — delta spec modifies the latency sub-requirement inside "generate_diff_markdown produces a Δ vs master table".
- No API changes, no dependency additions, no schema changes.
