## 1. Red — Failing Unit Test

- [x] 1.1 Create `task2/tests/test_trim_history.py` with a test that constructs a synthetic `messages` list containing a system message, multiple interleaved user-state messages, and 6 complete assistant-tool-call / tool-result groups (each group: one `role="assistant"` with `tool_calls`, followed by one `role="tool"`). Call `from agent.loop import trim_history` (which does not yet exist) and assert that when `keep_steps=4`, the 2 oldest tool-result groups and their paired assistant messages are absent from the returned list while all user-state messages and the system prompt are retained.
- [x] 1.2 Run `uv run pytest task2/tests/test_trim_history.py -x` from `task2/` and confirm it fails with `ImportError` (function not yet implemented). Record the exact failure line.

## 2. Green — Implement `trim_history`

- [x] 2.1 Add the `trim_history(messages: list[dict], keep_steps: int | None = None) -> list[dict]` function to `task2/agent/loop.py`, immediately below `_compact_messages`. The function SHALL:
  - Parse `keep_steps` from `HISTORY_TRIM_KEEP_STEPS` env var (int, default 4) if not provided explicitly.
  - Walk `messages` (skipping index 0, the system prompt) to identify tool-result groups: a group is one `role="assistant"` message with `tool_calls` followed by its paired `role="tool"` messages sharing those `tool_call_id` values.
  - Count groups from the most recent; drop groups older than `keep_steps` (both the assistant message and its paired tool results).
  - Never drop `role="user"` messages.
  - Return a new list without mutating the input.
- [x] 2.2 Wire the call into `loop()`: after the line `messages = _compact_messages(messages, _budget)` (line ~854), insert `messages = trim_history(messages)` so trim runs on every step before the LLM call.
- [x] 2.3 Run `uv run pytest task2/tests/test_trim_history.py -x` and confirm green.

## 3. Refactor Under Green

- [x] 3.1 Run `uv run pytest task2/` to confirm the full test suite passes (no regressions).
- [x] 3.2 Run `uv run ruff check task2/agent/loop.py task2/tests/test_trim_history.py` and fix any lint issues.
- [x] 3.3 Run `uv run ruff format task2/agent/loop.py task2/tests/test_trim_history.py` and commit the result.

## 4. Post-Implementation Benchmark Verification (manual gate)

- [ ] 4.1 Run `uv run python task2/scripts/bench.py --case webvoyager-1` (or equivalent benchmark invocation) against the local Qwen3.5 27B endpoint. Record `status` and `reason` from the output JSON.
- [ ] 4.2 Repeat step 4.1 two more times (3 total independent runs). Verify that at least 2 of 3 runs show `status="succeeded"` and `reason=null` within the 120s wall-clock budget. This is the acceptance criterion from ticket #97 — it is a manual verification step, not a pytest assertion.
- [ ] 4.3 If fewer than 2 of 3 runs succeed: inspect `step_breakdown` prompt-token counts. If tokens still grow beyond 21,000, reduce `HISTORY_TRIM_KEEP_STEPS` (e.g. try `2`) and re-run the benchmark before concluding.
