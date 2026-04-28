## Context

`CaseResult` in `task2/scripts/eval.py` is a frozen dataclass. All skip paths today converge on `_skipped_result()` which hard-codes `status="skipped"` with no further context. The scoreboard in `score.py` already filters skipped cases out of success-rate and percentile math but emits nothing about *why* they were skipped.

Two skip paths exist in `run_suite()` today:
1. `not live and not case.get("fixture", False)` → produces `_skipped_result(case)` with reason `live_disabled`.
2. A missing fixture file is currently not a guarded code path — `load_cases()` raises `ValueError` on a missing required field but does not check whether fixture paths referenced by the case actually exist. The ticket requires that a missing fixture file produce `skip_reason="fixture_missing"` rather than a hard crash.

`infra_unavailable` and `feature_not_implemented` are valid `skip_reason` literals required by the spec but no active code path sets them in this ticket. They are reserved for future tickets.

## Goals / Non-Goals

**Goals:**
- Add `skip_reason` field to `CaseResult` typed as `Literal["live_disabled", "infra_unavailable", "fixture_missing", "feature_not_implemented"] | None`.
- Enforce at construction: any `CaseResult` with `status="skipped"` MUST have a non-`None` `skip_reason`; an unrecognized reason value MUST raise `ValueError`.
- Wire `_skipped_result()` to accept a `reason` parameter and propagate it; caller in `run_suite()` passes `"live_disabled"`.
- Add a `fixture_path` optional field to case YAML; when present and the path does not exist, `run_suite()` produces `CaseResult(status="skipped", skip_reason="fixture_missing")` instead of crashing.
- Scoreboard: append a "Skipped" subsection after the per-case table (before mechanism rates) listing reason → count for every skipped case.

**Non-Goals:**
- Setting `infra_unavailable` or `feature_not_implemented` in any active code path — those are reserved.
- Changing results JSON shape for non-skipped cases — `skip_reason` is `null` and remains backwards-compatible.
- Modifying the exit-code logic (skipped cases already do not contribute to non-zero exit).

## Decisions

### D1: Enforcement in `__post_init__` vs. factory function

**Decision**: Use `__post_init__` on the frozen dataclass.

`CaseResult` is `@dataclass(frozen=True)`. Adding `__post_init__` is the idiomatic Python place to enforce field-level invariants. Alternatives (a factory classmethod, a validator in `_skipped_result`) would leave the door open for code that constructs `CaseResult` directly to bypass validation. `__post_init__` catches all construction sites.

### D2: Literal type vs. plain `str`

**Decision**: Use `Literal[...]` for the valid reason values, identical to how `failure_class` uses a string union.

`failure_class` in the existing codebase is `str | None`, not a `Literal`. However, the ticket spec explicitly requires rejection of unrecognized reasons at construction time — a `Literal` type annotation alone does not enforce that at runtime, so `__post_init__` will also check against an explicit `frozenset` of valid values. The `Literal` annotation communicates intent to type-checkers; the runtime check provides the enforcement.

### D3: Scoreboard placement

**Decision**: Insert "Skipped" subsection immediately after the per-case table rows but before the blank line that leads into the aggregate summary line.

This keeps skipped-case context visible near the case list without interrupting the pass-rate headline. The subsection is only emitted when there is at least one skipped case; if no cases were skipped, the block is omitted entirely.

### D4: `fixture_missing` skip path scope

**Decision**: Check `fixture_path` in `run_suite()` rather than in `load_cases()`.

`load_cases()` is a pure YAML parser; introducing path-existence checks there couples it to filesystem state and makes it harder to unit-test. `run_suite()` already contains all skip-or-run branching, so it is the right place to check `fixture_path` existence and emit `skip_reason="fixture_missing"`.

## Risks / Trade-offs

- **Backwards compatibility**: The `skip_reason` field is new on `CaseResult`. Old results JSON files will not have it; `score.py` reads `case.get("skip_reason")` with a default of `None`, so existing result files continue to parse cleanly.
- **Frozen dataclass with `__post_init__`**: Frozen dataclasses call `__post_init__` after `__init__`, so validation fires before the object is fully immutable — this is safe and is the documented pattern.
- **Golden snapshot**: `test_score_golden_snapshot_matches` compares output character-for-character. Adding the "Skipped" subsection will change the snapshot. The test must regenerate `sample_results_scoreboard.md` as part of the green step or the snapshot must be updated in the same PR.
