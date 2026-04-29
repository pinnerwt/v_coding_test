---
id: 28
slug: forward-shared-locatorcache-run-case-into
status: active
tier: 4
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related:
- 27
filed_pr: null
merged_pr: null
archived_at: null
trigger: ''
---

28. **Forward shared `LocatorCache` from `_run_case` into `loop()` and `locate()`** — ticket #27 added a `cache: LocatorCache | None` argument to `scripts/eval._run_case` and wired `run_suite` to construct one shared instance per parent case when `shared_cache: true`. The cache reaches `_run_case` correctly (the `test_run_suite_shared_cache_same_instance_passed_to_variants` test asserts this), but it stops there: `loop()`'s signature does not accept `cache`, so `_run_case` silently drops it before invoking `loop()`. As a result, the `maintenance-drift-rename` eval case does not actually exercise cache continuity across v1→v2 in production runs — only the unit-test mock does. Add a `locator_cache: LocatorCache | None = None` kwarg to `agent.loop.loop()`; thread it through to `agent.locate.locate()` (which already accepts a cache parameter); update `_run_case` to forward `cache` into `loop(..., locator_cache=cache)`. Tests: a fixture eval run on `maintenance-drift-rename` with a real (non-mocked) `loop()` produces a v2 case whose trace contains `LocateEvent(cache_action="invalidate")` because the v1 entry was a hit on the warm shared cache (assert via `_aggregate_diagnostics`); when `cache=None`, `loop()` constructs / uses its current default cache (no behavior change for the existing API server path); existing `loop()` tests still pass with no signature-change fixups required (default `None` stays back-compat).
