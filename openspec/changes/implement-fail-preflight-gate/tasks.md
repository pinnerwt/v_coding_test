## 1. Failing Tests (Red Phase)

- [x] 1.1 Write test `test_supervisor_event_premature_fail_literal` — construct `SupervisorEvent(run_id="r", seq=1, ts="", step_id=None, trigger_event_seq=0, classified_as="premature_fail", policy="halt", attempt=1)` and assert Pydantic validation succeeds and `event.classified_as == "premature_fail"`. Run `uv run pytest task2/tests/ -k "premature_fail_literal"` — confirm test fails because `"premature_fail"` is not yet in the `Literal`.
- [x] 1.2 Write test `test_loop_fail_step1_no_prior_action_is_rejected` — stub LLM emits `fail(reason="nothing here")` on step 1; assert `RunResult.status != "failed"` (loop does NOT terminate), and the `events` list contains a dict (or object) with `classified_as="premature_fail"`.
- [x] 1.3 Write test `test_loop_fail_step2_after_read_is_honored` — stub LLM emits `read()` on step 1 and `fail(reason="could not find result")` on step 2; assert `RunResult.status == "failed"` and no `premature_fail` event in `events`.
- [x] 1.4 Write test `test_loop_fail_irrecoverable_keyword_honored_on_step1` — stub LLM emits `fail(reason="login wall detected")` on step 1; assert `RunResult.status == "failed"` immediately and no `premature_fail` event in `events`.
- [x] 1.5 Write test `test_loop_fail_step1_after_successful_click_is_honored` — stub LLM emits `click(intent="Submit button")` (outcome ok via fixture) then `fail(reason="submit failed")` in the same step 1; assert `RunResult.status == "failed"` and no `premature_fail` event.
- [x] 1.6 Run `uv run pytest task2/tests/ -k "premature_fail or fail_step"` — confirm all five new tests fail for the expected reason (missing literal, missing gate logic).

## 2. Production Code (Green Phase)

- [x] 2.1 In `agent/trace.py`, add `"premature_fail"` to `SupervisorEvent.classified_as` Literal: `Literal["LocatorMiss","Ambiguous","NoEffect","FormError","NavDrift","Blocked","Timeout","premature_fail"]`.
- [x] 2.2 In `agent/loop.py`, add module-level constant: `_IRRECOVERABLE_REASONS: frozenset[str] = frozenset({"login wall", "captcha", "blocked"})`.
- [x] 2.3 In `agent/loop.py`, add private helper: `def _has_actionable_outcome(outcome: str) -> bool: return outcome in {"ok", "nav"}`.
- [x] 2.4 In `agent/loop.py`, initialize `_prior_act_outcomes: list[str] = []` at the start of `loop()` (alongside `step_num = 0`, `last_actions = []`, etc.).
- [x] 2.5 In `agent/loop.py`, update the `click` dispatch branch: after computing `outcome`, if `outcome in _CLICK_SUCCESS_OUTCOMES`, append `outcome` to `_prior_act_outcomes`.
- [x] 2.6 In `agent/loop.py`, update the `type` dispatch branch: after computing `fill_outcome`, if `fill_outcome == "ok"`, append `fill_outcome` to `_prior_act_outcomes`.
- [x] 2.7 In `agent/loop.py`, replace the `if tool_call.name == "fail":` block with the gated version:
  - Extract `reason = args.get("reason", "")`.
  - Compute `is_irrecoverable = any(kw in reason.lower() for kw in _IRRECOVERABLE_REASONS)`.
  - Compute `is_premature = step_num <= 1 and not any(_has_actionable_outcome(o) for o in _prior_act_outcomes) and not is_irrecoverable`.
  - If `is_premature`:
    - Emit `SupervisorEvent(classified_as="premature_fail", policy="halt", attempt=1)` via `_emit_supervisor_event` or append to `events` (when `trace_writer` is `None`).
    - Compute `nudge = f"you have {max_steps - step_num} steps left and have not attempted to interact — try \`click\`/\`type\` first."`.
    - Append `{"role": "tool", "tool_call_id": tool_call.id, "content": nudge}` to `messages`.
    - `continue` (do NOT call `_record_step`, do NOT return).
  - Else: keep the existing `_record_step` + `return RunResult(status="failed", ...)` path.
- [x] 2.8 Run `uv run pytest task2/tests/ -k "premature_fail or fail_step"` — confirm all five new tests pass.

## 3. Full Test Suite and Lint

- [x] 3.1 Run `uv run pytest task2/tests/agent/test_loop.py` — confirm no regressions in existing loop tests.
- [x] 3.2 Run `uv run pytest task2/tests/` — confirm full suite stays green.
- [x] 3.3 Run `uv run ruff check task2/` — fix any lint errors.
- [x] 3.4 Run `uv run ruff format task2/` — fix any formatting issues.

## 4. Benchmark Verification

- [ ] 4.1 Run `uv run python -m score` (or equivalent) to measure benchmark pass rate.
- [ ] 4.2 Confirm at least one of the 5 `read→fail` benchmark cases flips from red to green.
- [ ] 4.3 Confirm no previously-green benchmark cases regressed.
