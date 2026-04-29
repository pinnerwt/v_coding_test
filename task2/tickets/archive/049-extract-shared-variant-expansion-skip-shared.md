---
id: 49
slug: extract-shared-variant-expansion-skip-shared
status: archived
tier: 5
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related:
- 37
- 36
filed_pr: 86
merged_pr: null
archived_at: '2026-04-29'
trigger: 'surfaced by review subagent on PR #75 (iteration 1).'
---

49. **Extract shared variant-expansion + skip + shared-cache iteration helper.** `task2/scripts/eval.py::run_suite` (around lines 303-321) and `task2/scripts/benchmark.py::main` `--repeats > 1` branch (around lines 271-293) both implement: (a) read `parent_case.variants`, (b) build sub_cases with `id` suffixes per variant, (c) construct a single `LocatorCache(path=":memory:")` when `shared_cache=True and variants`, (d) skip cases via the same fixture-missing / live-disabled ladder. Each path will silently drift from the other when a new skip class or a per-variant cache strategy is added. Extract a helper `iter_runnable_subcases(parent_cases, *, live) -> Iterator[tuple[dict, LocatorCache | None, str | None]]` (yields `(case, shared_cache, skip_reason)`) in `eval.py` and consume it from both call sites. Tests: a parametrized case with two variants and `shared_cache=True` yields the same `LocatorCache` object for both sub_cases; a live-only case yields a `skip_reason="live_disabled"` when called with `live=False`; a missing-fixture case yields `skip_reason="fixture_missing"`. *Why useful:* eliminates a real DRY hazard — both paths must agree on skip semantics for the canary suite (#37) and the auto-diff feature (#36) to be correct. *Trigger:* surfaced by review subagent on PR #75 (iteration 1).
