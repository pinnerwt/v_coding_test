## 1. Red — write failing stuck-detection unit test

- [x] 1.1 In `task2/tests/agent/test_loop.py`, add `test_loop_stuck_repeat_exits_early`: use `_StubBrowserForCompaction`-style stub browser (with `patch("agent.loop.observe.build_observation", return_value=_LARGE_OBSERVATION)`) and a new `_AlwaysGotoClient` stub LLM that always returns `goto(url="about:blank")`. Call `loop("task", stub_browser, stub_llm, max_steps=20)` and assert `result.status == "failed"`, `result.reason == "stuck_repeat"`, and `result.steps == 3`.
- [x] 1.2 Run `uv run pytest task2/tests/agent/test_loop.py::test_loop_stuck_repeat_exits_early -x` from the repo root and confirm it fails with `AttributeError: 'RunResult' object has no attribute 'reason'` or `AssertionError` (not an import error).

## 2. Green — implement RunResult.reason field

- [x] 2.1 In `task2/agent/loop.py`, add `reason: str | None = None` as a field to the `RunResult` frozen dataclass (place it after `verifier` and before `steps` so it reads as a semantic qualifier, matching the design decision).
- [x] 2.2 Run the failing test again (`uv run pytest task2/tests/agent/test_loop.py::test_loop_stuck_repeat_exits_early -x`) — it should now advance past the `reason` attribute error and fail only on the `status`/`steps` assertions.

## 3. Green — implement K-buffer and early-exit in loop()

- [x] 3.1 In `task2/agent/loop.py`, add module-level constant `_STUCK_REPEAT_K: int = 3` near the other module-level constants (`_DEFAULT_CONTEXT_CHAR_BUDGET`, etc.).
- [x] 3.2 In `loop()`, initialize `_stuck_buf: list[str] = []` immediately after `_prior_act_outcomes` initialization.
- [x] 3.3 Inside the `for tool_call in response.tool_calls:` loop, after `args` is successfully parsed from `tool_call.arguments`, append the canonical entry `f"{tool_call.name}:{json.dumps(args, sort_keys=True)}"` to `_stuck_buf`. After the append, trim `_stuck_buf` to the last `_STUCK_REPEAT_K` entries with `_stuck_buf = _stuck_buf[-_STUCK_REPEAT_K:]`. Then check: if `len(_stuck_buf) == _STUCK_REPEAT_K` and `len(set(_stuck_buf)) == 1`, call `_record_step(step_num, t0, response, dispatched_tool_names, latency_ms_per_step, step_breakdown)` and return `RunResult(status="failed", reason="stuck_repeat", result=None, evidence=None, verifier=None, steps=step_num, prompt_tokens=cum_prompt_tokens, completion_tokens=cum_completion_tokens, usd=cum_usd, latency_ms_total=sum(latency_ms_per_step), latency_ms_per_step=latency_ms_per_step, step_breakdown=step_breakdown)`.
- [x] 3.4 Run `uv run pytest task2/tests/agent/test_loop.py::test_loop_stuck_repeat_exits_early -x` and confirm it passes (green).

## 4. Red → Green — write and pass healthy-alternation negative test

- [x] 4.1 In `task2/tests/agent/test_loop.py`, add `test_loop_stuck_repeat_no_false_positive_on_alternation`: use `_StubBrowserForCompaction`-style stub browser and a new `_AlternatingGotoClient` stub LLM that returns `goto(url="http://a")`, `goto(url="http://b")`, `goto(url="http://a")` in sequence then exhausts to `_response_no_tool_call()`. Call `loop("task", stub_browser, stub_llm, max_steps=20)` and assert `result.status == "timeout"` and `result.reason is None` (no stuck detection on alternating URLs).
- [x] 4.2 Run `uv run pytest task2/tests/agent/test_loop.py::test_loop_stuck_repeat_no_false_positive_on_alternation -x` and confirm it passes immediately (the implementation from task 3 already handles this correctly).
- [x] 4.3 Run the full test file to confirm no regressions: `uv run pytest task2/tests/agent/test_loop.py`.

## 5. Cleanup — lint and format

- [x] 5.1 Run `uv run ruff check task2/` from the repo root and fix any lint errors introduced.
- [x] 5.2 Run `uv run ruff format task2/` and confirm no diff remains.
- [x] 5.3 Re-run `uv run pytest task2/tests/agent/test_loop.py` to confirm green bar after formatting.
