## 1. RED — Write failing tests

- [ ] 1.1 Create `task2/tests/test_iter_runnable_subcases.py` with a parametrized fixture case having two variants and `shared_cache=True`; assert same `LocatorCache` instance is yielded for both sub-cases and `skip_reason` is `None` for both.
- [ ] 1.2 Add test: live-only case (no `fixture: true`) with `live=False` yields one tuple with `skip_reason="live_disabled"` and `shared_cache=None`.
- [ ] 1.3 Add test: case with `fixture: true` and `fixture_path` pointing to a non-existent path yields one tuple with `skip_reason="fixture_missing"` and `shared_cache=None`.
- [ ] 1.4 Add test: non-variantized fixture case (no `variants`, no `fixture_path`) yields exactly one tuple with `skip_reason=None`, `shared_cache=None`, and the original case dict unchanged.
- [ ] 1.5 Add test: case with `variants: ["v1", "v2"]`, `fixture: true`, and no `shared_cache` key yields two tuples both with `shared_cache=None` and `skip_reason=None`.
- [ ] 1.6 Run `uv run pytest task2/tests/test_iter_runnable_subcases.py` and confirm all five tests FAIL with `ImportError` or `AttributeError` (function does not exist yet).

## 2. GREEN — Implement iter_runnable_subcases

- [ ] 2.1 Hoist `from agent.locator_cache import LocatorCache` to module level in `task2/scripts/eval.py` (remove the deferred import inside `run_suite`).
- [ ] 2.2 Add `from typing import Iterator` to `task2/scripts/eval.py` imports (if not already present).
- [ ] 2.3 Implement `iter_runnable_subcases(parent_cases: list[dict], *, live: bool) -> Iterator[tuple[dict, LocatorCache | None, SkipReason | None]]` in `task2/scripts/eval.py` immediately above `run_suite`, following the skip ladder described in the spec: fixture_path missing → `"fixture_missing"`, else not live and no fixture → `"live_disabled"`, else `None`.
- [ ] 2.4 Run `uv run pytest task2/tests/test_iter_runnable_subcases.py` and confirm all five new tests PASS.
- [ ] 2.5 Run `uv run pytest task2/` and confirm no existing tests are broken.

## 3. REFACTOR — Consume iterator in run_suite

- [ ] 3.1 Replace the inline variant-expansion and skip-ladder block in `run_suite` (lines 312-335) with `for case, shared_cache, skip_reason in iter_runnable_subcases(cases, live=live): ...`, calling `_skipped_result(case, skip_reason)` when `skip_reason` is non-None and `_run_case(case, ..., cache=shared_cache, ...)` otherwise.
- [ ] 3.2 Run `uv run pytest task2/` and confirm full suite is green.

## 4. REFACTOR — Consume iterator in benchmark.py

- [ ] 4.1 Add `iter_runnable_subcases` to the import list from `scripts.eval` at the top of `task2/scripts/benchmark.py`.
- [ ] 4.2 Replace the inline variant-expansion block in `benchmark.py::main`'s `--repeats > 1` branch (lines 294-318) with `for case, shared_cache, skip_reason in iter_runnable_subcases(all_cases, live=args.live): ...`, calling `aggregate_repeats(case, ..., cache=shared_cache)` when `skip_reason` is `None` and emitting a skipped `AggregatedCaseResult` otherwise.
- [ ] 4.3 Run `uv run pytest task2/` and confirm full suite is still green.

## 5. Final cleanup

- [ ] 5.1 Run `uv run ruff check .` from `task2/` and fix any linting issues.
- [ ] 5.2 Run `uv run ruff format .` from `task2/` if needed to pass format checks.
- [ ] 5.3 Run `uv run pytest task2/` one final time and confirm full suite passes with no warnings.
