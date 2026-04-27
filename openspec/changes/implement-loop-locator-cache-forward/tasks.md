## 1. Red Phase — Write Failing Tests First

- [ ] 1.1 In `task2/tests/test_loop.py`, add a test `test_loop_accepts_locator_cache_kwarg` that calls `loop(..., locator_cache=None)` and asserts it returns a `RunResult` (confirms the kwarg is accepted; will fail if not yet added to signature).
- [ ] 1.2 In `task2/tests/test_loop.py`, add a test `test_loop_forwards_cache_to_locate` that passes a `MagicMock`-instrumented `LocatorCache` as `locator_cache` and verifies `locate()` is called with `cache=<that instance>` when the LLM emits `read(intent="Submit button")`.
- [ ] 1.3 In `task2/tests/test_eval.py`, add a test `test_run_case_forwards_cache_to_loop` that patches `scripts.eval.loop` with a side-effect that captures kwargs, calls `_run_case(..., cache=<mock_cache>)`, and asserts `loop` was called with `locator_cache=<mock_cache>`.
- [ ] 1.4 In `task2/tests/test_eval.py`, add the real-loop fixture test `test_maintenance_drift_rename_real_loop_cache_invalidation` that: (a) uses `playwright_chromium` + `fixture_server`, (b) mocks the LLM to emit `read(intent="Submit button")` then `done`, (c) runs `loop()` with `locator_cache=cache` against v1 and v2 fixture pages, (d) asserts `cache_events["invalidations"] >= 1` from `_aggregate_diagnostics` on the v2 run.
- [ ] 1.5 Run `uv run pytest task2/tests/test_loop.py task2/tests/test_eval.py -x` from `task2/` and confirm new tests fail for the expected reasons (signature error / assertion error), all pre-existing tests pass.

## 2. Green Phase — Minimal Implementation

- [ ] 2.1 In `task2/agent/loop.py`, add `locator_cache: LocatorCache | None = None` to the `loop()` function signature (after `trace_writer`). Add the necessary `TYPE_CHECKING` import for `LocatorCache` at the top of the file (mirror how `locate.py` does it).
- [ ] 2.2 In `task2/agent/loop.py`, update `_dispatch` to accept `locator_cache: LocatorCache | None = None` as a fifth argument. In the `read` branch where `intent` is non-empty, replace the `_locate_with_supervisor(page, intent, supervisor)` call with `locate(page, intent, cache=locator_cache)` — import `locate` from `agent.locate` alongside the existing `locate_l1`, `locate_l2`, `parse_intent` imports.
- [ ] 2.3 In `task2/agent/loop.py`, update the `_dispatch` call site inside `loop()` to pass `locator_cache` as the fifth argument.
- [ ] 2.4 In `task2/scripts/eval.py`, update `_run_case` to pass `locator_cache=cache` when calling `loop()`.
- [ ] 2.5 Run `uv run pytest task2/tests/test_loop.py task2/tests/test_eval.py -x` from `task2/` and confirm all tests (including new ones) pass.
- [ ] 2.6 Run the full test suite `uv run pytest task2/` from `task2/` and confirm no regressions.

## 3. Lint and Format

- [ ] 3.1 Run `uv run ruff check --fix task2/agent/loop.py task2/scripts/eval.py` from `task2/` and confirm zero errors.
- [ ] 3.2 Run `uv run ruff format task2/agent/loop.py task2/scripts/eval.py` from `task2/` and confirm no diff.
- [ ] 3.3 Run `uv run ruff check task2/tests/test_loop.py task2/tests/test_eval.py` from `task2/` and confirm zero errors.

## 4. Verify Acceptance Criteria

- [ ] 4.1 Confirm `loop()` signature now reads: `def loop(task, browser, llm_client, *, max_steps=20, events=None, run_id=None, trace_writer=None, locator_cache=None)`.
- [ ] 4.2 Confirm all existing callers of `loop()` (in `task2/api/`, `task2/scripts/`, test mocks) require no changes.
- [ ] 4.3 Confirm `test_maintenance_drift_rename_real_loop_cache_invalidation` passes — this is the acceptance criterion that proves the end-to-end cache forwarding works in production-path code.
- [ ] 4.4 Confirm `test_run_suite_shared_cache_same_instance_passed_to_variants` still passes (no regression on the ticket #27 assertion).
