## Context

Task 2's CI workflow (`task2-benchmark.yml`) currently only verifies that a `results.json` file exists and has a `run_at` timestamp newer than the merge-base commit. It does not inspect whether any case passed or failed. This means a branch that makes every single eval case fail can still land on master — the gate is literally a no-op for quality.

The ticket asks for a "canary suite": a tiny, curated set of trivially-easy cases (fixture-backed, 1–2 step, no live network) that must pass on every CI run. A canary regression should hard-block the PR. Non-canary regressions remain advisory (they appear in the scoreboard diff comment but do not block merge).

Current state:
- `eval/cases/fixture-heading.yaml` and `fixture-count.yaml` exist and are `fixture: true` — they already run in CI without `--live`. Neither is marked as "must pass."
- `scripts/benchmark.py` writes `results.json`; `scripts/score.py` reads it and produces a scoreboard. Neither interprets canary semantics.
- `task2-benchmark.yml` runs `python -m scripts.benchmark --verify` which only checks the file's timestamp.

## Goals / Non-Goals

**Goals:**
- A `canary: true` boolean field in case YAML that marks a case as "must always pass."
- A standalone `scripts/canary_gate.py` module (CLI: `uv run python -m scripts.canary_gate --results <path>`) that reads `results.json`, checks canary case outcomes, and exits 1 if any canary is non-passing, or exits 0 with a printed warning if all canaries pass but non-canaries failed.
- Tag `fixture-heading` and `fixture-count` as canary cases, plus add one new canary case `canary-read-h1` (a 1-step fixture case that reads the H1 of the existing heading fixture).
- A new "Canary gate" step in `task2-benchmark.yml` that invokes `canary_gate.py` after `--verify` and blocks merge on exit code 1.
- Pure-Python unit tests (no Playwright, no LLM) for the gate logic using synthetic `results.json` dicts.

**Non-Goals:**
- Changing the existing `--verify` step or `verify_benchmark()` logic.
- Making non-canary failures block CI.
- Integrating canary status into the scoreboard display (that is ticket #33's domain).
- Changing how `run_suite` or `_run_case` behave — the canary field is metadata consumed only by the gate script.

## Decisions

### Decision 1: `canary: true` field in case YAML, not a separate category value

**Chosen**: Add `canary: bool` (default `false`) to the existing case YAML schema alongside the `category` field.

**Rationale**: The ticket mentions `category: canary` as *one possible mechanism* but also says "e.g. `fixture-heading`, `fixture-count`" — cases that already have `category: read-and-summarize` and `category: search-and-extract`. Changing their `category` would break the scoreboard's suite-bucketing logic in `score.py` (which uses `category`-based ID prefixes). A separate `canary: true` boolean is additive and non-breaking.

**Alternative considered**: New `category: canary` value. Rejected because it would break the `SUITE_THRESHOLDS` ID-prefix bucketing and require coordinated changes to `score.py`.

### Decision 2: Canary gate is a standalone script, not a flag on `benchmark.py` or `score.py`

**Chosen**: `scripts/canary_gate.py` is a new module invoked separately.

**Rationale**: The gate must be callable after the `--verify` step without re-running the benchmark. The results file is already committed to the branch; the gate just reads it. Adding a `--canary-gate` flag to `benchmark.py` would conflate running the benchmark with gating. A separate module keeps the gate independently testable and lets CI call it without any LLM/browser deps.

**Alternative considered**: Add a `--canary-gate` flag to `score.py`. Rejected because `score.py` currently has no exit-code semantics beyond what `main()` returns implicitly.

### Decision 3: Canary gate reads `canary: true` from the results JSON (not re-reading YAML)

**Chosen**: The gate reads the `canary` field from each case entry in `results.json` (i.e., `benchmark.py` must serialize it from the case dict into `CaseResult`/`AggregatedCaseResult`).

**Rationale**: The results file is a self-contained snapshot. The gate script should not need access to `eval/cases/*.yaml` — it just reads the pre-written artifact. This is consistent with how `score.py` and `baseline_diff.py` work.

**Implementation note**: `CaseResult` (in `eval.py`) needs a `canary: bool = False` field added so that `asdict()` serializes it. `AggregatedCaseResult` (in `benchmark.py`) needs the same. `_run_case` must accept and forward `canary` from the case dict. `run_suite` and `benchmark.main` must pass `canary=case.get("canary", False)` when constructing `CaseResult`.

### Decision 4: "Passing" definition for canary gate

A canary case is **passing** if its `status` is in `{"succeeded", "unverified"}` (i.e., `PASS_STATUSES` from `eval.py`). Status `"skipped"` counts as **failing** for canary purposes — a canary that was skipped is a gate failure, because canary cases are always `fixture: true` and should never be skipped in normal CI.

**Rationale**: A canary that silently skips gives false confidence. If a canary is skipped (e.g. because its fixture was deleted), the gate must catch it.

### Decision 5: New `canary-read-h1` case reuses the existing heading fixture

The heading fixture HTML already exists at `task2/tests/fixtures/` (used by `fixture-heading`). `canary-read-h1` is a second canary case that reads the same fixture's H1 but with a 1-step budget, stress-testing that the agent can do the simplest possible task. This gives the canary suite three cases total — enough to be meaningful without being slow.

## Risks / Trade-offs

- **`CaseResult`/`AggregatedCaseResult` field addition**: Adding `canary: bool` to both dataclasses is a small schema change. Existing `results.json` files written before this change will not have `canary` in each case entry; `canary_gate.py` must treat a missing field as `False` (not canary) via `.get("canary", False)`. Backward-compat is preserved.
- **Skipped canary = gate failure**: This is intentional but may surprise a developer who accidentally deletes a fixture. The error message from the gate should explain why the case was skipped.
- **CI step order**: The "Canary gate" step runs after `--verify` (which checks the file timestamp) but uses the same `results.json`. If `--verify` passes but `results.json` was written before the canary field existed, the gate will see no canary cases and exit 0 with a notice. This is acceptable — the gate is only effective after the new canary cases land.
