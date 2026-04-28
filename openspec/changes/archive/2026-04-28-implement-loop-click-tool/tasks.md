## 1. Failing Tests (Red Phase)

- [x] 1.1 Write test `test_tools_list_includes_click` — assert `TOOLS` contains entry with `function.name == "click"`, `intent` in `parameters.properties`, and `intent` in `required`
- [x] 1.2 Write test `test_loop_click_to_done` — fixture page with a `<button>Submit</button>`, stub LLM emits `click(intent="Submit button")` then `done(...)`; assert `RunResult.status == "succeeded"` in ≤ 4 steps
- [x] 1.3 Write test `test_loop_click_outcome_nav` — fixture page with a button that navigates to a second URL on click; assert `ActEvent(outcome="nav")` is emitted in trace
- [x] 1.4 Write test `test_loop_click_l1_miss_supervisor_escalation` — fixture page with a non-semantic button (no ARIA role); assert `SupervisorEvent(policy="next_tier")` emitted and click is retried at L2
- [x] 1.5 Run `uv run pytest task2/tests/agent/test_loop.py -k "click"` — confirm all four new tests fail for the right reason (no `click` in `TOOLS` / `_dispatch`)

## 2. Production Code (Green Phase)

- [x] 2.1 Add `click` fixture HTML to `task2/tests/fixtures/` — a minimal page with `<button>Submit</button>` and a nav-triggering page with a button that links to a second page
- [x] 2.2 Update `ToolName` literal in `loop.py` to include `"click"`
- [x] 2.3 Append `click` entry to `TOOLS` list in `loop.py` — `function.name="click"`, `parameters.properties={"intent": {"type": "string"}}`, `required=["intent"]`
- [x] 2.4 Add `_emit_act_event` helper in `loop.py` mirroring `_emit_locate_event` / `_emit_supervisor_event` pattern
- [x] 2.5 Add `click` branch in `_dispatch`: call `_locate_with_supervisor`, record `url_before`, call `page.locator(result.selector).click(timeout=5000)`, detect nav/ok/timeout/error, emit `ActEvent`, return outcome string
- [x] 2.6 Run `uv run pytest task2/tests/agent/test_loop.py -k "click"` — confirm all four new tests pass

## 3. Full Test Suite and Lint

- [x] 3.1 Run `uv run pytest task2/tests/agent/test_loop.py` — confirm no regressions in existing loop tests
- [x] 3.2 Run `uv run pytest task2/tests/` — confirm full suite stays green
- [x] 3.3 Run `uv run ruff check task2/` — fix any lint errors
- [x] 3.4 Run `uv run ruff format task2/` — fix any formatting issues

## 4. Benchmark Verification

- [x] 4.1 Run `uv run python -m score` (or equivalent) to measure benchmark pass rate improvement
- [x] 4.2 Confirm `correction-l1-miss-l2-hit`, `drift-submit-form-v1`, `drift-submit-form-v2`, `maintenance-drift-rename-v1`, `maintenance-drift-rename-v2` all flip from red to green
