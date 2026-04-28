## 1. Red — failing tests first (TDD)

- [ ] 1.1 Write `task2/tests/test_canary_gate.py` with Tests A–E (all five synthetic-JSON test cases from spec). Run `uv run pytest tests/test_canary_gate.py` and confirm they all fail with `ModuleNotFoundError` or `ImportError` (module does not exist yet).
- [ ] 1.2 Confirm `uv run ruff check .` is clean before touching production code.

## 2. Schema changes — add `canary` field to CaseResult and AggregatedCaseResult

- [ ] 2.1 In `task2/scripts/eval.py`, add `canary: bool = False` field to `CaseResult` (after `skip_reason`).
- [ ] 2.2 In `task2/scripts/eval.py`, update `_skipped_result` to accept and forward `canary=case.get("canary", False)` to `CaseResult`.
- [ ] 2.3 In `task2/scripts/eval.py`, update `run_suite` to pass `canary=case.get("canary", False)` when calling `_run_case` — and update `_run_case` signature to accept and forward `canary: bool = False` to `CaseResult`.
- [ ] 2.4 In `task2/scripts/benchmark.py`, add `canary: bool = False` field to `AggregatedCaseResult`.
- [ ] 2.5 In `task2/scripts/benchmark.py`, update `_skipped_aggregate` to accept and forward `canary=case.get("canary", False)`.
- [ ] 2.6 In `task2/scripts/benchmark.py`, update `aggregate_repeats` to pass `canary=case.get("canary", False)` to `AggregatedCaseResult`.
- [ ] 2.7 Run existing tests: `uv run pytest tests/` — confirm no regressions from field additions.

## 3. Case YAML changes — tag canary cases

- [ ] 3.1 Add `canary: true` to `task2/eval/cases/fixture-heading.yaml`.
- [ ] 3.2 Add `canary: true` to `task2/eval/cases/fixture-count.yaml`.
- [ ] 3.3 Create `task2/eval/cases/canary-read-h1.yaml` with the spec-required fields (`id: canary-read-h1`, `canary: true`, `fixture: true`, `budget.steps: 1`, etc.). Reuse the same fixture page as `fixture-heading` (check what `fixture_path` or fixture URL `fixture-heading` uses and mirror it).
- [ ] 3.4 Run `uv run python -m scripts.eval --case fixture-heading` with a mocked/stub run and verify the output JSON contains `"canary": true`.

## 4. canary_gate module — make tests green

- [ ] 4.1 Create `task2/scripts/canary_gate.py` implementing the CLI contract from the spec: `--results <path>`, reads JSON, identifies canary cases via `.get("canary", False)`, applies gate logic, prints appropriate messages, exits 0 or 1.
- [ ] 4.2 Ensure `canary_gate.py` imports `PASS_STATUSES` from `scripts.eval` and uses no Playwright/LLM deps.
- [ ] 4.3 Run `uv run pytest tests/test_canary_gate.py` — all five tests must pass.
- [ ] 4.4 Run `uv run ruff check .` and `uv run ruff format .` — must be clean.

## 5. CI workflow — add canary gate step

- [ ] 5.1 In `.github/workflows/task2-benchmark.yml`, add the "Canary gate" step after the "Verify benchmark recorded for branch" step.
- [ ] 5.2 The step computes `SAFE_BRANCH` (same pattern as the "Post diff as PR comment" step) and runs `uv run python -m scripts.canary_gate --results benchmark/${SAFE_BRANCH}/results.json`.
- [ ] 5.3 Confirm the step has `set -euo pipefail` so exit code 1 from the gate propagates to the CI job.

## 6. Spec delta — update bench-repeats forward reference

- [ ] 6.1 Confirm `openspec/changes/implement-canary-suite/specs/bench-repeats/spec.md` contains the MODIFIED requirement with the forward reference to "canary suites" removed (it mentions drift suite only). This was already authored in the spec artifact above — verify the wording is correct.

## 7. Full green bar verification

- [ ] 7.1 Run the full test suite: `uv run pytest tests/` from `task2/` — all tests green.
- [ ] 7.2 Run `uv run ruff check .` — no lint errors.
- [ ] 7.3 Smoke-test the gate manually: write a synthetic `results.json` to a temp file with one canary-failed case and run `uv run python -m scripts.canary_gate --results <tmpfile>` — confirm exit code 1.
- [ ] 7.4 Smoke-test the gate with all-canary-pass + one non-canary-fail — confirm exit code 0 and `WARNING` in output.
