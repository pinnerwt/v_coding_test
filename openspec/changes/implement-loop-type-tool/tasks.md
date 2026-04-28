## 1. Failing Tests (Red Phase)

- [ ] 1.1 Write test `test_tools_list_includes_type` — assert `TOOLS` contains an entry with `function.name == "type"`, `"intent"` and `"text"` in `parameters.properties` (both `type == "string"`), and both `"intent"` and `"text"` in `parameters.required`
- [ ] 1.2 Write test `test_loop_type_fills_textbox` — fixture page with `<input type="text" placeholder="Email">`, stub LLM emits `type(intent="Email textbox", text="hello@example.com")` then `done(...)`; assert `RunResult.status == "succeeded"` in ≤ 4 steps and the `ActEvent(outcome="ok")` is in the trace
- [ ] 1.3 Write test `test_loop_type_l1_miss_returns_tool_error_loop_continues` — fixture page with a textbox that has no ARIA role but has a placeholder; stub LLM emits `type(intent="Nonexistent textbox", text="foo")` (intent that L1 and L2 both miss) then `done(...)`; assert the tool-result message starts with `"Error:"` and the loop continues (returns `RunResult` rather than crashing)
- [ ] 1.4 Run `uv run pytest task2/tests/agent/test_loop.py -k "type"` — confirm all new tests fail for the expected reason (no `type` in `TOOLS` / `_dispatch`)

## 2. Production Code (Green Phase)

- [ ] 2.1 Add `type` fixture HTML to `task2/tests/fixtures/` — a minimal page `loop_type_textbox.html` with `<input type="text" placeholder="Email" id="email">` and no other inputs; the page title is "Type Textbox Fixture"
- [ ] 2.2 Update `ToolName` literal in `loop.py` to include `"type"`: `Literal["goto", "read", "click", "type", "done", "fail"]`
- [ ] 2.3 Append `type` entry to `TOOLS` list in `loop.py`:
  - `function.name = "type"`
  - `parameters.properties = {"intent": {"type": "string", ...}, "text": {"type": "string", ...}}`
  - `required = ["intent", "text"]`
- [ ] 2.4 Add `type` branch in `_dispatch` (after the `click` branch, before the unknown-tool fallthrough):
  - Extract `intent_val` and `text_val` from args; return error string if either is absent or non-string
  - Call `_locate_or_error_msg(page, intent_val, supervisor, cache=locator_cache, trace_writer=trace_writer, run_id=run_id, step_id=step_id)`; return the error string if locate failed
  - Record `t_fill = time.monotonic()`
  - Call `page.locator(locate_result.selector).fill(text_val, timeout=5000)` inside a try/except block:
    - `PlaywrightTimeoutError` → `outcome = "timeout"`
    - Other `PlaywrightError` → `outcome = "error"`
    - Success → `outcome = "ok"`
  - Compute `elapsed_ms`
  - Call `_emit_act_event(trace_writer=…, run_id=…, tool="type", args={"intent": intent_val, "text": text_val}, outcome=outcome, ms=elapsed_ms, step_id=step_id)`
  - Return `f"Typed into {intent_val!r} (ok)"` on success or `f"Error: type {outcome} for intent {intent_val!r}"` on failure
- [ ] 2.5 Run `uv run pytest task2/tests/agent/test_loop.py -k "type"` — confirm all new tests pass

## 3. Full Test Suite and Lint

- [ ] 3.1 Run `uv run pytest task2/tests/agent/test_loop.py` — confirm no regressions in existing loop tests
- [ ] 3.2 Run `uv run pytest task2/tests/` — confirm full suite stays green
- [ ] 3.3 Run `uv run ruff check task2/` — fix any lint errors
- [ ] 3.4 Run `uv run ruff format task2/` — fix any formatting issues

## 4. Benchmark Verification

- [ ] 4.1 Run `uv run python -m score` (or equivalent) to measure benchmark pass rate
- [ ] 4.2 Confirm no previously-green benchmark cases regressed
- [ ] 4.3 Note any cases that flip red→green due to `type` now being available (expected: zero today per ticket analysis; record result for future reference)
