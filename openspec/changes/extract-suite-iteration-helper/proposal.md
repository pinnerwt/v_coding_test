## Why

`run_suite` in `eval.py` and the `--repeats > 1` block in `benchmark.py::main` each independently implement variant expansion, shared-cache construction, and the fixture-missing / live-disabled skip ladder. When a new skip class or per-variant cache strategy is added, both paths must be updated in sync or silently diverge — a real DRY hazard that already affects the canary suite (#37) and auto-diff feature (#36).

## What Changes

- Introduce `iter_runnable_subcases(parent_cases, *, live) -> Iterator[tuple[dict, LocatorCache | None, str | None]]` in `task2/scripts/eval.py` — a single authoritative place for variant expansion, shared-cache construction, and skip-reason determination.
- Refactor `run_suite` (lines 313-321) to consume the iterator instead of its inline expand-and-skip block.
- Refactor `benchmark.py::main`'s `--repeats > 1` block (lines 298-306) to consume the same iterator.
- Add parametrized tests covering the five scenarios (two-variant shared-cache, live-disabled skip, fixture-missing skip, non-variant, variants-no-shared-cache).

## Capabilities

### New Capabilities
- `eval-runner`: adds `iter_runnable_subcases` shared helper requirement to the existing `eval-runner` spec.

### Modified Capabilities
- `eval-runner`: new `## ADDED Requirements` section for the helper's contract; existing `Variant expansion`, `live_disabled skip path sets skip_reason`, and `fixture_missing skip path sets skip_reason` requirements are **not** changed.

## Impact

- `task2/scripts/eval.py` — new function `iter_runnable_subcases`; `run_suite` body simplified.
- `task2/scripts/benchmark.py` — `--repeats > 1` block simplified.
- `task2/tests/` — new or extended test file covering the helper's five scenarios.
- No changes to public API, YAML schema, results JSON format, or CLI flags.
