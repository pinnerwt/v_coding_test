## 1. Red — Write Failing Tests

- [x] 1.1 Write test `test_no_progress_constant_fingerprint_bails_at_step_4`: stub LLM emitting `read(intent=f"x{i}")` each step, stub browser returning constant `ax_fingerprint`; assert `RunResult.reason == "no_progress"` and `steps == 4`
- [x] 1.2 Write test `test_no_progress_alternating_fingerprint_runs_to_completion`: same stub LLM but browser alternates between two fingerprints; assert loop does NOT exit with `reason="no_progress"`
- [x] 1.3 Write test `test_no_progress_click_ok_prevents_bail`: stub LLM emitting `click(intent="button")` each step, constant fingerprint, click always returns `"Clicked 'button' (ok)"`; assert loop does NOT exit with `reason="no_progress"`
- [x] 1.4 Run `uv run pytest` from `task2/` and confirm all three new tests fail (red) for the expected reason (missing `_no_progress_buf` logic)

## 2. Extend RunResultReason Literal

- [x] 2.1 In `task2/agent/loop.py`, extend `RunResultReason` Literal to include `"no_progress"` alongside existing values (`"stuck_repeat"`, `"no_tool_call_repeat"`, `"seconds_budget"`)
- [x] 2.2 Run `uv run ruff check task2/agent/loop.py` — must be clean

## 3. Implement _no_progress_buf Logic

- [x] 3.1 Add `_NO_PROGRESS_K: int = 4` module-level constant in `task2/agent/loop.py`
- [x] 3.2 Initialize `_no_progress_buf: list[tuple[str, bool]] = []` at the start of `loop()` alongside the existing `_stuck_buf = []` and `_consecutive_no_tool_call_steps = 0`
- [x] 3.3 Track `any_action_succeeded_this_step: bool = False` at the top of each step iteration; set to `True` when a `click` or `type` tool call's result does not start with `"Error:"`
- [x] 3.4 After the tool-call dispatch loop completes (and only when there were tool calls — i.e. the no-tool-call branch was NOT taken), capture `post_fp = observe.build_observation(browser, []).get("ax_fingerprint")` and append `(post_fp, any_action_succeeded_this_step)` to `_no_progress_buf`
- [x] 3.5 Trim `_no_progress_buf` to the last `_NO_PROGRESS_K` entries
- [x] 3.6 Check bail condition: `len(_no_progress_buf) == _NO_PROGRESS_K` AND `len({fp for fp, _ in _no_progress_buf}) == 1` AND `all(not ok for _, ok in _no_progress_buf)`; if true, call `_record_step(...)` then return `RunResult(status="failed", reason="no_progress", result=None, evidence=None, verifier=None, steps=step_num, prompt_tokens=cum_prompt_tokens, completion_tokens=cum_completion_tokens, usd=cum_usd, latency_ms_total=sum(latency_ms_per_step), latency_ms_per_step=latency_ms_per_step, step_breakdown=step_breakdown)`

## 4. Green — Verify Tests Pass

- [x] 4.1 Run `uv run pytest task2/tests/ -k "no_progress"` — all three new tests must be green
- [x] 4.2 Run full test suite `uv run pytest task2/` — no regressions; `test_stuck_repeat_k_identical_tool_calls_terminates` must still pass
- [x] 4.3 Run `uv run ruff check task2/` and `uv run ruff format --check task2/` — both must be clean

## 5. Validate Spec Delta Completeness

- [x] 5.1 Confirm `RunResultReason` Literal in code matches the MODIFIED spec (includes `"no_progress"`)
- [x] 5.2 Confirm `_NO_PROGRESS_K = 4` in code matches spec constant
- [x] 5.3 Confirm `_no_progress_buf` check placement is post-dispatch, not inside the tool-call loop
- [ ] 5.4 Run `openspec validate implement-no-progress-stuck-detection --strict` — must pass
