## 1. Red — Write Failing Tests

- [x] 1.1 Write test `test_run_case_propagates_reason_seconds_budget` in `task2/tests/test_eval_case_reason.py` (stubbed `scripts.eval.loop` → `RunResult(reason="seconds_budget", ...)`).
- [x] 1.2 Write test `test_run_case_propagates_reason_no_progress`.
- [x] 1.3 Write test `test_run_case_propagates_reason_stuck_repeat`.
- [x] 1.4 Write test `test_run_case_propagates_reason_no_tool_call_repeat` (covers the fourth `RunResultReason` literal value).
- [x] 1.5 Write test `test_run_case_succeeded_has_reason_none` (asserts `CaseResult.reason is None` on the happy path).
- [x] 1.6 Write test `test_bench_json_includes_reason_field_on_every_case` (asserts every serialized case dict has a `"reason"` key).
- [x] 1.7 Write test `test_bench_json_reason_is_null_on_succeeded` (asserts `data["cases"][0]["reason"] is None` for a succeeded case).
- [x] 1.8 Write test `test_skipped_result_has_reason_none` (asserts `_skipped_result(...).reason is None`).
- [x] 1.9 Write test `test_run_case_exception_path_has_reason_none` (asserts the exception-path constructor leaves `reason=None`).
- [x] 1.10 Run `cd task2 && uv run pytest tests/test_eval_case_reason.py` and confirm tests fail (red) for the expected reason (missing `reason` field on `CaseResult`).

## 2. Green — Add reason field and wire it

- [x] 2.1 In `task2/scripts/eval.py`, add `reason: str | None = None` to the `CaseResult` dataclass immediately after the `failure_detail` field.
- [x] 2.2 In the success-path `CaseResult(...)` constructor at `task2/scripts/eval.py:310-329`, add `reason=run_result.reason` to the keyword arguments.
- [x] 2.3 Leave the exception-path `CaseResult(...)` constructor at `task2/scripts/eval.py:287-297` unchanged (relies on `reason=None` default).
- [x] 2.4 Run `cd task2 && uv run pytest tests/test_eval_case_reason.py` — all nine new tests must be green.

## 3. Verify — No regressions

- [x] 3.1 Run full test suite `cd task2 && uv run pytest` — no regressions; pre-existing tests that load benchmark JSON or construct `CaseResult` must still pass.
- [x] 3.2 Run `cd task2 && uv run ruff check .` and `cd task2 && uv run ruff format --check .` — both must be clean.

## 4. Validate Spec Delta Completeness

- [x] 4.1 Confirm the `reason` field appears in the `CaseResult` dataclass exactly as specified in `openspec/changes/implement-propagate-runresult-reason-to-caseresult/specs/eval-runner/spec.md`.
- [x] 4.2 Confirm `reason=run_result.reason` is passed only on the success-path (post-`loop()`) constructor, not the exception-path constructor.
- [x] 4.3 Run `openspec validate implement-propagate-runresult-reason-to-caseresult --strict` — must pass.
