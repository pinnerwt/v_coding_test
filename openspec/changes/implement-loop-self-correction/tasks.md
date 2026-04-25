## 1. Red — Failing Test

- [ ] 1.1 Create `task2/tests/fixtures/loop_self_correction.html` — a page with a `<button aria-label="action">Submit</button>` so that L1 `get_by_role("button", name="Submit")` returns zero matches while L2 `filter(has_text="Submit")` returns exactly one match.
- [ ] 1.2 Add `test_loop_self_correction` to `task2/tests/agent/test_loop.py` using `fixture_server` + `playwright_chromium` + `_FakeLLMClient`. The mock LLM sequence: step 1 → `goto(fixture_url)`, step 2 → `read(intent="Submit button")`, step 3 → `done(result={"clicked": true}, evidence={"url": fixture_url, "text_snippet": "Submit"})`. Assert `result.status == "succeeded"`.
- [ ] 1.3 Run `uv run pytest task2/tests/agent/test_loop.py::test_loop_self_correction -x` from `task2/` and confirm it fails (either with `LocatorMiss` propagating unhandled or the loop returning `timeout`/`failed` because the LLM never reaches `done`).

## 2. Green — Wire Supervisor into Loop

- [ ] 2.1 Import `Supervisor` from `agent.supervisor` and `locate_l1`, `locate_l2` from `agent.locate` in `task2/agent/loop.py`.
- [ ] 2.2 Add a `Supervisor` instance as a local variable inside `loop()` (constructed once per run with default `max_attempts=3`).
- [ ] 2.3 In `_dispatch`, replace the single `locate(page, intent)` call in the `read` branch with a supervisor-driven two-step: call `locate_l1(page, role=role, name=name)` inside a `try/except LocatorMiss`; on `reason="zero_matches"`, call `supervisor.handle(miss, current_tier="L1_ax")`; if `decision.next_tier == "L2_dom"`, call `locate_l2(page, role=role, name=name)`; if escalation is halted or L2 also fails, return an error string as the tool result. Update `_dispatch` signature to accept `supervisor` as a parameter, and thread it from `loop()`.
- [ ] 2.4 Run `uv run pytest task2/tests/agent/test_loop.py::test_loop_self_correction -x` and confirm it passes.
- [ ] 2.5 Run the full test suite `uv run pytest task2/tests/` and confirm all existing tests still pass.

## 3. Lint and Format

- [ ] 3.1 Run `uv run ruff check . --fix` from `task2/` and resolve any lint errors.
- [ ] 3.2 Run `uv run ruff format .` from `task2/` to auto-format changed files.
- [ ] 3.3 Confirm `uv run ruff check .` exits clean.

## 4. Refactor Under Green (if needed)

- [ ] 4.1 Review `_dispatch` for clarity — ensure the supervisor escalation block is readable and follows the pattern described in design.md Decision 3. Refactor only if tests remain green.
- [ ] 4.2 Verify no new imports of `locate()` (the full-ladder function) are introduced; the `read` dispatch must use the explicit `locate_l1` / `locate_l2` calls so the supervisor path is exercised.
