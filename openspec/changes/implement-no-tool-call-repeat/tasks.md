## 1. Red — Write failing tests

- [x] 1.1 In `task2/tests/agent/test_loop.py` (or the existing loop test file), add a test `test_no_tool_call_repeat_exits_at_k` using a stub `LLMClient` that always returns `ChatResponse(content="thinking...", tool_calls=[])`: assert `loop()` returns `RunResult(status="failed", reason="no_tool_call_repeat", steps=3)`.
- [x] 1.2 Add a control test `test_no_tool_call_repeat_resets_on_tool_call`: stub returns no-tool-call on steps 1–2, then `goto(url="http://example.com")` on step 3, then no-tool-call for remaining steps up to `max_steps=20`; assert `RunResult.status == "timeout"` and `RunResult.steps == 20`.
- [x] 1.3 Run `uv run pytest task2/tests/agent/test_loop.py -k "no_tool_call_repeat" -x` from `task2/` — confirm both tests fail (red).

## 2. Green — Implement the counter

- [x] 2.1 In `task2/agent/loop.py`, add the module-level constant `_NO_TOOL_CALL_K: int = 3` alongside `_STUCK_REPEAT_K`.
- [x] 2.2 Extend `RunResultReason` from `Literal["stuck_repeat"]` to `Literal["stuck_repeat", "no_tool_call_repeat"]`.
- [x] 2.3 In `loop()`, initialize `_consecutive_no_tool_call_steps: int = 0` alongside `_stuck_buf`.
- [x] 2.4 In the `if not response.tool_calls:` branch (currently `_record_step; continue`): increment `_consecutive_no_tool_call_steps`; if it reaches `_NO_TOOL_CALL_K`, call `_record_step(...)` and return `RunResult(status="failed", reason="no_tool_call_repeat", result=None, evidence=None, verifier=None, steps=step_num, prompt_tokens=cum_prompt_tokens, completion_tokens=cum_completion_tokens, usd=cum_usd, latency_ms_total=sum(latency_ms_per_step), latency_ms_per_step=latency_ms_per_step, step_breakdown=step_breakdown)`; otherwise `continue`.
- [x] 2.5 In the `for tool_call in response.tool_calls:` path (at the top of the tool-dispatch loop, before any dispatch), reset `_consecutive_no_tool_call_steps = 0`.
- [x] 2.6 Run `uv run pytest task2/tests/agent/test_loop.py -k "no_tool_call_repeat" -x` — confirm both tests pass (green).
- [x] 2.7 Run full test suite `uv run pytest task2/` — confirm no regressions.

## 3. Lint and format

- [x] 3.1 Run `uv run ruff check task2/agent/loop.py task2/tests/agent/test_loop.py` — fix any issues.
- [x] 3.2 Run `uv run ruff format task2/agent/loop.py task2/tests/agent/test_loop.py` — apply formatting.
- [x] 3.3 Confirm `uv run ruff check task2/` exits clean.

## 4. Final verification

- [x] 4.1 Run full test suite one more time: `uv run pytest task2/` — all green.
- [x] 4.2 Confirm `git diff task2/` touches only `agent/loop.py` and the test file (no accidental changes to other modules).
