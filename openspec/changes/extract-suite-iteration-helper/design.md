## Context

`task2/scripts/eval.py::run_suite` (lines 312-321) and `task2/scripts/benchmark.py::main`'s `--repeats > 1` block (lines 294-318) each independently implement three concerns:

1. **Variant expansion** — read `parent_case.get("variants")`, build sub-cases with id-suffix per variant.
2. **Shared-cache construction** — build one `LocatorCache(path=":memory:")` when `shared_cache: true` and variants are present.
3. **Skip-reason ladder** — check `fixture_path` existence (→ `"fixture_missing"`) then `live` flag vs `fixture: true` (→ `"live_disabled"`).

The existing `SkipReason` type alias and `_skipped_result` helper live in `eval.py`. `benchmark.py` imports `_run_case` and constructs `LocatorCache` directly. Any new skip class or cache strategy must be duplicated across both files — the DRY hazard noted in ticket #49.

## Goals / Non-Goals

**Goals:**
- Extract a single `iter_runnable_subcases` generator that encapsulates all three concerns.
- Replace the inline blocks in both `run_suite` and `benchmark.py::main` with calls to the iterator.
- Add tests covering the five key scenarios (two-variant shared-cache identity, live-disabled skip, fixture-missing skip, non-variant baseline, variants-no-shared-cache).
- Pass `uv run ruff check .` and full `uv run pytest` green after all steps.

**Non-Goals:**
- Adding new skip classes or cache strategies (the ticket is about extraction, not extension).
- Changing the public CLI interface or results JSON schema.
- Modifying any requirement already in `openspec/specs/eval-runner/spec.md`.

## Decisions

### Decision: Iterator signature uses `Literal` for skip_reason type

`iter_runnable_subcases` signature:
```
iter_runnable_subcases(
    parent_cases: list[dict],
    *,
    live: bool,
) -> Iterator[tuple[dict, LocatorCache | None, SkipReason | None]]
```

The third element of the tuple uses the existing `SkipReason` Literal alias (`"live_disabled" | "infra_unavailable" | "fixture_missing" | "feature_not_implemented"`) rather than bare `str | None`. This keeps the closed-set contract enforced by the type system and by `CaseResult.__post_init__`, consistent with the `/new_task2` Step 6 rule.

**Alternatives considered:** Return `str | None` validated at boundary — rejected because validation would need to be duplicated at every consumer site.

### Decision: Helper lives in `eval.py`, not a new module

Both current consumers (`eval.py` and `benchmark.py`) already import from `eval.py`. Adding a third module purely to hold one function introduces an indirection layer with no second caller. The function remains alongside `run_suite` in `eval.py`.

**Alternatives considered:** New `task2/scripts/runner_utils.py` — rejected (no second caller; CLAUDE.md explicitly prohibits abstractions for hypothetical second callers).

### Decision: `LocatorCache` import hoisted to module level in `eval.py`

Currently `from agent.locator_cache import LocatorCache` is a deferred import inside `run_suite`. The helper must construct `LocatorCache` before any `_run_case` call, so the import needs to be accessible at function scope. Moving it to module level avoids repeating the deferred import pattern and aligns with how `benchmark.py` already imports it at the top of the file.

**Alternatives considered:** Keep the deferred import inside the helper — acceptable but inconsistent with `benchmark.py`. Module-level import is simpler.

### Decision: Helper does NOT call `_run_case` or `_skipped_result`

The helper only determines **what** to do (yield the prepared sub-case plus cache and skip_reason); each consumer remains responsible for calling `_run_case` or emitting a `CaseResult`. This keeps the generator free of side-effects and makes it trivially testable without mocking the LLM or browser.

**Alternatives considered:** Have the helper call `_run_case` directly — rejected because the benchmark consumer wraps `_run_case` in `aggregate_repeats`; a unified call would require the helper to accept a callable, adding complexity the test surface doesn't justify.

### Decision: Shared-cache object is constructed once per parent_case in the helper

The `LocatorCache(path=":memory:")` instance is created inside the helper when `shared_cache: true` and variants are present, then yielded identically for every sub-case of that parent. This is the behavior already present in both inline blocks; the extraction preserves it exactly.

## Risks / Trade-offs

- **benchmark.py skip ladder gap**: The current `benchmark.py` `--repeats > 1` block (lines 309-318) does NOT have the fixture-missing / live-disabled skip check inline — it relies on `aggregate_repeats` handling skips differently. After refactoring, the helper will apply the skip ladder to the benchmark path too. This is the **intended** outcome (the ticket's stated goal is to make both paths agree on skip semantics) but must be verified by running the full test suite.
  - Mitigation: Existing fixture-missing and live-disabled tests in `test_eval.py` already cover `run_suite`; add parallel coverage for the benchmark path in the new test file.

- **Import-order side-effects**: Hoisting `LocatorCache` to module level in `eval.py` means it is imported even when no shared cache is needed. `LocatorCache` has no known import-time side effects; the risk is negligible.

## Migration Plan

TDD sequence (matches tasks.md):

1. **RED** — Write failing tests for the five helper scenarios.
2. **GREEN** — Implement `iter_runnable_subcases` in `eval.py`; new tests pass, existing tests untouched.
3. **REFACTOR** — Replace `run_suite` inline block with the iterator. Full pytest green.
4. **REFACTOR** — Replace `benchmark.py::main` inline block with the iterator. Full pytest green.
5. **CLEAN** — `uv run ruff check .` clean.

No deployment steps required; the change is internal to the eval/benchmark scripts.

## Open Questions

None. All skip classes, cache strategies, and consumer call sites are known and bounded.
