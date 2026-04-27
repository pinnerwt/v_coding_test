## 1. Red Phase — Write Failing Tests First

- [x] 1.1 In `task2/tests/test_loop.py`, add a test `test_loop_accepts_locator_cache_kwarg` that calls `loop(..., locator_cache=None)` and asserts it returns a `RunResult` (confirms the kwarg is accepted; will fail if not yet added to signature).
- [x] 1.2 In `task2/tests/test_loop.py`, add a test `test_loop_forwards_cache_to_locate` that passes a real `LocatorCache(":memory:")` as `locator_cache`, runs against the `drift/submit-form/v1` fixture, and asserts `cache.get(origin, "Submit button")` returns an entry with `role="button"` after the run.
- [x] 1.3 In `task2/tests/test_eval.py`, add a test `test_run_case_forwards_cache_to_loop` that patches `scripts.eval.loop` with a side-effect that captures kwargs, calls `_run_case(..., cache=<mock_cache>)`, and asserts `loop` was called with `locator_cache=<mock_cache>`.
- [x] 1.4 In `task2/tests/test_eval.py`, add the real-loop fixture test `test_maintenance_drift_rename_real_loop_cache_invalidation` that: (a) uses `playwright_chromium` + `fixture_server`, (b) mocks the LLM to emit `read(intent="Submit button")` then `done`, (c) runs `loop()` with `locator_cache=cache` against v1 and v2 fixture pages, (d) asserts `cache_events["invalidations"] >= 1` from `_aggregate_diagnostics` on the v2 run.
- [x] 1.5 Run `uv run pytest task2/tests/test_loop.py task2/tests/test_eval.py -x` from `task2/` and confirm new tests fail for the expected reasons (signature error / assertion error), all pre-existing tests pass.
- [x] 1.6 In `task2/tests/agent/test_loop.py`, add `test_loop_emits_locate_event_write_on_first_resolve` — runs `loop()` against v1 with a fresh cache and a `TraceWriter`, asserts exactly one `LocateEvent` row with `cache_action="write"` and `intent="Submit button"`.
- [x] 1.7 In `task2/tests/agent/test_loop.py`, add `test_loop_emits_locate_event_invalidate_then_write_on_drift` — shares one cache across a v1 then v2 run, asserts the v2 trace contains a `cache_action="invalidate"` row before a `cache_action="write"` row.

## 2. Green Phase — Minimal Implementation

- [x] 2.1 In `task2/agent/loop.py`, add `locator_cache: LocatorCache | None = None` to the `loop()` function signature (after `trace_writer`). Add the necessary `TYPE_CHECKING` import for `LocatorCache` at the top of the file (mirror how `locate.py` does it).
- [x] 2.2 In `task2/agent/loop.py`, update `_dispatch` to accept `locator_cache: LocatorCache | None = None`, `trace_writer: TraceWriter | None = None`, `run_id: str | None = None`. In the `read` branch where `intent` is non-empty, pass them through as `_locate_with_supervisor(page, intent, supervisor, cache=locator_cache, trace_writer=trace_writer, run_id=run_id)`. Add the same kwargs to `_locate_with_supervisor` and embed a probe → invalidate → L1/L2-with-supervisor → write cycle there, mirroring `agent.locate.locate()`'s pattern. Reuse `CacheEntry`, `_origin_from_url`, and `_canonical_ax_fingerprint` via lazy imports inside the function.
- [x] 2.3 In `task2/agent/loop.py`, update the `_dispatch` call site inside `loop()` to pass `locator_cache`, `trace_writer=trace_writer`, `run_id=run_id`.
- [x] 2.4 In `task2/scripts/eval.py`, update `_run_case` to pass `locator_cache=cache` when calling `loop()`.
- [x] 2.5 Run `uv run pytest task2/tests/test_loop.py task2/tests/test_eval.py -x` from `task2/` and confirm all tests (including new ones) pass.
- [x] 2.6 Run the full test suite `uv run pytest task2/` from `task2/` and confirm no regressions.
- [x] 2.7 In `task2/agent/loop.py`, add a module-private helper `_emit_locate_event(*, trace_writer, run_id, intent, tier, outcome, cache_action, chosen)` modeled on `_emit_plan_event`: no-op when `trace_writer is None or run_id is None`, otherwise allocate `seq` via `trace_writer.next_seq(run_id)`, build a `LocateEvent`, and `trace_writer.append_event(event)`.
- [x] 2.8 In `_locate_with_supervisor`, emit a `LocateEvent` with `cache_action="read"` + `outcome="hit"` + `tier="cache"` + `chosen={role, selector, ax_fingerprint}` from the cached entry on the read-hit return path.
- [x] 2.9 In `_locate_with_supervisor`, emit a `LocateEvent` with `cache_action="invalidate"` + `outcome="miss"` + `tier="cache"` whenever `cache.invalidate(...)` is called (both the `L4_vision` branch and the fingerprint-mismatch branch).
- [x] 2.10 In `_locate_with_supervisor`, emit a `LocateEvent` with `cache_action="write"` + `outcome="hit"` + `tier=<resolved tier>` + `chosen={role, selector, ax_fingerprint}` immediately after the post-ladder `cache.put(...)`.

## 3. Lint and Format

- [x] 3.1 Run `uv run ruff check --fix task2/agent/loop.py task2/scripts/eval.py` from `task2/` and confirm zero errors.
- [x] 3.2 Run `uv run ruff format task2/agent/loop.py task2/scripts/eval.py` from `task2/` and confirm no diff.
- [x] 3.3 Run `uv run ruff check task2/tests/test_loop.py task2/tests/test_eval.py` from `task2/` and confirm zero errors.

## 4. Verify Acceptance Criteria

- [x] 4.1 Confirm `loop()` signature now reads: `def loop(task, browser, llm_client, *, max_steps=20, events=None, run_id=None, trace_writer=None, locator_cache=None)`.
- [x] 4.2 Confirm all existing callers of `loop()` (in `task2/api/`, `task2/scripts/`, test mocks) require no changes.
- [x] 4.3 Confirm `test_maintenance_drift_rename_real_loop_cache_invalidation` passes — this is the acceptance criterion that proves the end-to-end cache forwarding works in production-path code.
- [x] 4.4 Confirm `test_run_suite_shared_cache_same_instance_passed_to_variants` still passes (no regression on the ticket #27 assertion).
