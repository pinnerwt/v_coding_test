# Tasks

## 1. Failing tests first (TDD red)

- [ ] 1.1. Add `test_is_near_budget_*` tests to `task2/tests/test_eval.py` covering: (a) `steps=4, budget.steps=5, usd=0, budget.usd=1, latency_ms_total=0, budget.seconds=30 → True` (80% step axis), (b) `steps=3, budget.steps=5, ... → False` (79% step axis, just below threshold), (c) usd-axis at `usd=0.04, budget.usd=0.05 → True`, (d) seconds-axis at `latency_ms_total=24_000, budget.seconds=30 → True`, (e) `steps=4, budget.steps=5` but missing `budget.usd`/`budget.seconds` keys still trips on the present axis.
- [ ] 1.2. Add `test_run_case_sets_near_budget_when_succeeded_at_80pct_steps` and `test_run_case_clears_near_budget_when_succeeded_below_80pct` to `task2/tests/test_eval.py`. Construct a `RunResult` with `status="succeeded"`, `steps=4`, `usd=0.0`, `latency_ms_total=0`, `result={"title":"x"}`, `evidence={"url":"http://x","text_snippet":"x"}`, `verifier={"ok":True,"reasons":[]}`. Patch `scripts.eval.loop` to return it. Assert `result.near_budget is True` for the 80% case and `False` for the 79% case (steps=3).
- [ ] 1.3. Add `test_run_case_failed_status_has_near_budget_false` to `task2/tests/test_eval.py` — a `RunResult` with `status="timeout"`, `steps=5, budget.steps=5` returns `near_budget=False` because the flag is suppressed on non-passing statuses.
- [ ] 1.4. Add `test_render_case_status_appends_warning_when_near_budget` to `task2/tests/test_score.py` — call `_render_case_status({"status":"succeeded","near_budget":True})` and assert the returned string contains "⚠️"; without `near_budget` (or `near_budget=False`) the warning is absent.
- [ ] 1.5. Run `cd task2 && uv run pytest task2/tests/test_eval.py task2/tests/test_score.py -k 'near_budget or near_budget'` from the repo root and confirm the new tests fail with `AttributeError`/`assert` against current code. Do not proceed until red.

## 2. Make tests green

- [ ] 2.1. Add `near_budget: bool = False` field to `CaseResult` in `task2/scripts/eval.py` (after `canary` / before any post-init validators).
- [ ] 2.2. Add `_NEAR_BUDGET_THRESHOLD = 0.80` and `def _is_near_budget(steps: int, usd: float, latency_ms_total: int, budget: dict) -> bool` in `task2/scripts/eval.py`. Implementation: for each `(metric, key, divisor)` in `[(steps, "steps", 1), (usd, "usd", 1), (latency_ms_total, "seconds", 1000)]`, if `budget.get(key)` is positive, compute `metric / divisor / budget[key]`; if any ratio is `>= _NEAR_BUDGET_THRESHOLD`, return `True`. Return `False` otherwise.
- [ ] 2.3. Wire `_is_near_budget` into `_run_case`: in the post-loop success path (the `return CaseResult(...)` after `_classify_failure`), compute `near_budget = run_result.status in PASS_STATUSES and _is_near_budget(run_result.steps, run_result.usd, run_result.latency_ms_total, case.get("budget", {}))` and pass it. Do not set the flag on the early-exception `return CaseResult(...)` path inside the `except` clause (status is `failed`).
- [ ] 2.4. Update `_render_case_status` in `task2/scripts/score.py` to append `" ⚠️"` to the returned string when `case.get("near_budget", False)`. Keep the existing rendering unchanged for `near_budget=False`.
- [ ] 2.5. Run `cd task2 && uv run pytest task2/tests/test_eval.py task2/tests/test_score.py` and confirm all tests pass.

## 3. Refactor and quality gates

- [ ] 3.1. Run `cd task2 && uv run ruff check . && uv run ruff format --check .` and address any findings.
- [ ] 3.2. Run the full `cd task2 && uv run pytest` and confirm zero regressions.
- [ ] 3.3. Re-read the diff for incidental scope creep (e.g. unrelated docstrings, comment additions) and remove anything not directly required by the failing tests.
