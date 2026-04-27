## 1. Red — PlanEvent step_id tests

- [ ] 1.1 In `task2/tests/agent/test_loop.py`, add `test_loop_with_trace_writer_initial_plan_event_step_id`: call `loop()` with a `:memory:` `TraceWriter` opened on a real `run_id`, assert the `PlanEvent` with `reason="initial"` has `step_id == f"{run_id}:step-1"`.
- [ ] 1.2 Add `test_loop_with_trace_writer_replan_event_step_id`: trigger a replan via supervisor halt on step 2 (use existing mock fixtures), assert the `PlanEvent` with `reason="replan"` has `step_id == f"{run_id}:step-2"`.
- [ ] 1.3 Add `test_loop_in_memory_events_plan_event_step_id_with_run_id`: call `loop()` with `events=[]` and `run_id="test-run"` but no `trace_writer`; assert the `PlanEvent` in `events` has `step_id == "test-run:step-1"`.
- [ ] 1.4 Add `test_loop_in_memory_events_plan_event_step_id_no_run_id`: call `loop()` with `events=[]` and no `run_id`; assert the `PlanEvent` in `events` has `step_id is None` (no regression).
- [ ] 1.5 Run `uv run pytest task2/tests/agent/test_loop.py -k "step_id"` from `task2/` and confirm all new tests fail for the expected reason (`step_id` is `None` instead of the expected value).

## 2. Red — LocateEvent step_id tests

- [ ] 2.1 In `task2/tests/agent/test_loop.py`, add `test_loop_emit_locate_event_step_id_on_cache_write`: call `loop()` with `run_id`, `locator_cache=<fresh cache>`, and a `TraceWriter` open on `run_id`; LLM emits `read(intent="Submit button")` on step 2 then `done`; assert the `LocateEvent` with `cache_action="write"` has `step_id == f"{run_id}:step-2"`.
- [ ] 2.2 Add `test_loop_emit_locate_event_step_id_on_cache_invalidate`: warm a cache from a v1 fixture run; run `loop()` on a v2 fixture page with the same cache, `run_id`, and `TraceWriter`; assert the `LocateEvent` with `cache_action="invalidate"` has `step_id` matching the step number at which the locate was triggered.
- [ ] 2.3 Add `test_loop_emit_locate_event_step_id_on_cache_hit`: use a warm cache (no fingerprint mismatch) for a second run on the v1 fixture; assert the `LocateEvent` with `cache_action="read"` and `outcome="hit"` has the correct `step_id`.
- [ ] 2.4 Run `uv run pytest task2/tests/agent/test_loop.py -k "step_id"` and confirm all new tests fail.

## 3. Green — Thread step_id into _emit_plan_event

- [ ] 3.1 In `task2/agent/loop.py`, add `step_id: str | None` parameter to `_emit_plan_event` (after the existing parameters). Forward it into `PlanEvent(step_id=step_id, ...)` instead of `step_id=None`.
- [ ] 3.2 Inside `loop()`, compute the step identifier as `_step_id = f"{run_id}:step-{step_num}" if run_id is not None else None` once per step iteration (immediately after `step_num += 1`).
- [ ] 3.3 Update the initial plan `_emit_plan_event` call-site (step 1) to pass `step_id=_step_id`.
- [ ] 3.4 Update the replan `_emit_plan_event` call-site (supervisor-halt boundary) to pass `step_id=_step_id` (using the `step_num` at the halt, which is the current value of `step_num`).
- [ ] 3.5 Run `uv run pytest task2/tests/agent/test_loop.py -k "plan_event and step_id"` — confirm `PlanEvent` step_id tests pass.

## 4. Green — Thread step_id into _dispatch and _locate_with_supervisor

- [ ] 4.1 Add `step_id: str | None = None` parameter to `_emit_locate_event` (the private helper); forward it into `LocateEvent(step_id=step_id, ...)` instead of `step_id=None`.
- [ ] 4.2 Update all four `_emit_locate_event` call-sites inside `_locate_with_supervisor` to pass `step_id=step_id`.
- [ ] 4.3 Add `step_id: str | None = None` keyword parameter to `_locate_with_supervisor`; pass it through to `_emit_locate_event` at each call-site.
- [ ] 4.4 Add `step_id: str | None = None` keyword parameter to `_dispatch`; pass it through to `_locate_with_supervisor` in the `read` branch.
- [ ] 4.5 Update the `_dispatch` call-site inside `loop()` to pass `step_id=_step_id`.
- [ ] 4.6 Run `uv run pytest task2/tests/agent/test_loop.py -k "step_id"` — confirm all new step_id tests pass.
- [ ] 4.7 Run `uv run pytest task2/tests/agent/test_loop.py` (full file) — confirm no regressions in existing tests.

## 5. Full suite and lint

- [ ] 5.1 Run `uv run pytest task2/` from `task2/` — confirm green bar across all tests.
- [ ] 5.2 Run `uv run ruff check task2/agent/loop.py` — confirm zero errors.
- [ ] 5.3 Run `uv run ruff format task2/agent/loop.py` — confirm no diff (or apply and recheck).
- [ ] 5.4 Run `uv run ruff check task2/tests/agent/test_loop.py` — confirm zero errors.

## 6. Acceptance verification

- [ ] 6.1 Confirm `loop()` signature reads: `def loop(task, browser, llm_client, *, max_steps=20, events=None, run_id=None, trace_writer=None, locator_cache=None)` — no new top-level parameters added (step_id is derived internally).
- [ ] 6.2 Confirm `_emit_plan_event` signature includes `step_id: str | None` parameter.
- [ ] 6.3 Confirm `_emit_locate_event`, `_locate_with_supervisor`, and `_dispatch` each include `step_id: str | None = None`.
- [ ] 6.4 Confirm `grep -n "step_id=None" task2/agent/loop.py` returns zero matches in the `LocateEvent(...)` and `PlanEvent(...)` constructors (the hardcoded `None` is gone).
- [ ] 6.5 Run the full test suite one final time: `uv run pytest task2/` — confirm green.
