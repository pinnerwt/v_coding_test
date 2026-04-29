## 1. Red — Write Failing Tests

- [ ] 1.1 Write test `test_run_case_propagates_reason_seconds_budget` in `task2/tests/test_eval_case_reason.py`: monkeypatch `scripts.eval.loop` with a stub returning `RunResult(status="timeout", reason="seconds_budget", ...)`; invoke `_run_case` on a minimal in-memory `Case`; assert the returned `CaseResult.reason == "seconds_budget"`.
- [ ] 1.2 Write test `test_run_case_propagates_reason_no_progress`: monkeypatch `scripts.eval.loop` with a stub returning `RunResult(status="failed", reason="no_progress", ...)`; assert `CaseResult.reason == "no_progress"`.
- [ ] 1.3 Write test `test_run_case_succeeded_has_reason_none`: monkeypatch `scripts.eval.loop` with a stub returning `RunResult(status="succeeded", reason=None, ...)`; assert `CaseResult.reason is None`.
- [ ] 1.4 Write test `test_bench_json_includes_reason_field` in `task2/tests/test_eval_case_reason.py`: invoke `run_suite` on a tiny in-memory fixture-only case list with stubbed loop; load the written JSON; assert every `case` dict has a `"reason"` key (value may be `None`).
- [ ] 1.5 Run `cd task2 && uv run pytest tests/test_eval_case_reason.py` and confirm all four tests fail (red) for the expected reason (missing `reason` field on `CaseResult`).

## 2. Green — Add reason field and wire it

- [ ] 2.1 In `task2/scripts/eval.py`, add `reason: str | None = None` to the `CaseResult` dataclass immediately after the `failure_detail` field.
- [ ] 2.2 In the success-path `CaseResult(...)` constructor at `task2/scripts/eval.py:310-329`, add `reason=run_result.reason` to the keyword arguments.
- [ ] 2.3 Leave the exception-path `CaseResult(...)` constructor at `task2/scripts/eval.py:287-297` unchanged (relies on `reason=None` default).
- [ ] 2.4 Run `cd task2 && uv run pytest tests/test_eval_case_reason.py` — all four new tests must be green.

## 3. Verify — No regressions

- [ ] 3.1 Run full test suite `cd task2 && uv run pytest` — no regressions; pre-existing tests that load benchmark JSON or construct `CaseResult` must still pass.
- [ ] 3.2 Run `cd task2 && uv run ruff check .` and `cd task2 && uv run ruff format --check .` — both must be clean.

## 4. Validate Spec Delta Completeness

- [ ] 4.1 Confirm the `reason` field appears in the `CaseResult` dataclass exactly as specified in `openspec/changes/implement-propagate-runresult-reason-to-caseresult/specs/eval-runner/spec.md`.
- [ ] 4.2 Confirm `reason=run_result.reason` is passed only on the success-path (post-`loop()`) constructor, not the exception-path constructor.
- [ ] 4.3 Run `openspec validate implement-propagate-runresult-reason-to-caseresult --strict` — must pass.
