## Why

The agent's self-correction and self-maintenance mechanisms (escalation ladder L1→L2, supervisor halt → replan, AX-fingerprint cache invalidation) exist in production code but are invisible to the eval suite: `tests/test_eval.py` only checks case count and result shape on drift variants, and no test exercises the supervisor-halt → replan path or the cache-invalidation path end-to-end. Without measured evidence, the brief's headline criterion ("substance of the self-correction / self-maintenance mechanisms") cannot be demonstrated to a reviewer.

## What Changes

- **`CaseResult`** gains three new diagnostic fields — `escalations: list[dict]`, `replans: int`, `cache_events: dict` — populated by aggregating `LocateEvent`, `SupervisorEvent`, and `PlanEvent` rows read from the trace after each case run. No new instrumentation is added; this is pure read-side aggregation.
- **Three new eval fixture cases** under `task2/eval/cases/` cover mechanism paths that the existing suite never exercises: `correction-l1-miss-l2-hit.yaml` (L1 → L2 escalation), `correction-replan.yaml` (supervisor halt → replan), and `maintenance-drift-rename.yaml` (warm-cache invalidation on a v2 re-run in the same process).
- **`tests/test_eval.py`** gains assertions that for each new case the relevant `CaseResult` diagnostic field is non-zero, so removing the mechanism in code makes the test go red.
- **`scripts/score.py`** is extended to surface per-case `escalations`, `replans`, and `cache_events` columns and overall mechanism-firing rates in the scoreboard markdown.
- **`task2/README.md`** gains a "Self-correction & self-maintenance — measured" subsection linking to the latest scoreboard and naming the three diagnostic cases, plus an honest list of remaining gaps.
- **Three new HTML fixture files** under `task2/tests/fixtures/` support the new eval cases: a page with no accessible button name (forces L1 miss → L2), a page that navigates to a dead-end so the supervisor halts (forces replan), and a drift rename page pair (v1/v2 sharing the fixture server in the same run so the cache is warm on v1 when v2 invalidates).

## Capabilities

### New Capabilities

- `eval-proof-metrics`: Extension of `CaseResult` with `escalations`, `replans`, and `cache_events` fields, populated by aggregating trace rows from the run's SQLite trace DB after `loop()` returns. Includes the aggregation helper that reads `LocateEvent`, `SupervisorEvent`, and `PlanEvent` rows by `run_id`.
- `eval-proof-cases`: Three new eval YAML case files under `task2/eval/cases/` and their supporting HTML fixtures under `task2/tests/fixtures/`. Each case's only success path exercises a specific mechanism: L1→L2 escalation, halt→replan, or cache invalidation.
- `score-mechanism-columns`: Extension of `scripts/score.py` to add per-case mechanism columns (`escalations`, `replans`, `cache_invalidations`) and an overall mechanism-firing rate summary block beneath the existing scoreboard.

### Modified Capabilities

- `eval-metrics`: `CaseResult` gains three new optional fields with zero/empty defaults for backward compatibility (`escalations: list[dict] = field(default_factory=list)`, `replans: int = 0`, `cache_events: dict = field(default_factory=dict)`). The results JSON schema gains those keys.
- `score-script`: `generate_scoreboard()` is extended to emit mechanism-firing columns; existing column order and aggregate summary lines are unchanged.
- `eval-runner`: `_run_case` is extended to pass a `TraceWriter` (in-memory SQLite) to `loop()`, read trace events after the run, aggregate them into the new `CaseResult` fields, and expose a `run_id` per case.
- `drift-suite`: The new `maintenance-drift-rename.yaml` case uses `variants: [v1, v2]` sharing a per-suite `LocatorCache` instance so the cache is warm on v1 when v2 runs; the eval runner's variant-expansion path must be amended to preserve the shared cache across variant sub-runs when the case has `shared_cache: true`.

## Impact

- `task2/scripts/eval.py` — extend `CaseResult`; wire `TraceWriter` into `_run_case`; add trace-aggregation helper.
- `task2/scripts/score.py` — add mechanism columns to `generate_scoreboard()`.
- `task2/eval/cases/correction-l1-miss-l2-hit.yaml` — new file.
- `task2/eval/cases/correction-replan.yaml` — new file.
- `task2/eval/cases/maintenance-drift-rename.yaml` — new file (uses `variants: [v1, v2]`, `shared_cache: true`).
- `task2/tests/fixtures/correction_l1_miss.html` — new file (no accessible button name, L1 misses, L2 hits).
- `task2/tests/fixtures/correction_replan_deadend.html` — new file (a page with no useful content that causes the supervisor to halt).
- `task2/tests/fixtures/drift/rename/v1/index.html` — new file (accessible button named "Submit").
- `task2/tests/fixtures/drift/rename/v2/index.html` — new file (accessible name changed to "Send", L1 fingerprint mismatch triggers cache invalidation).
- `task2/tests/test_eval.py` — new assertions for the three cases.
- `task2/README.md` — new subsection.
- No new Python packages.
