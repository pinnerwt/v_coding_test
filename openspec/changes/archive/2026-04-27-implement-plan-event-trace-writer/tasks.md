## 1. Failing Tests (Red)

- [x] 1.1 In `task2/tests/agent/test_loop.py`, add `test_loop_with_trace_writer_plan_event_has_real_run_id`: call `loop()` with a `:memory:` `TraceWriter` (opened with a real `run_id`) and assert the JSONL row for `kind="plan"` has `run_id` equal to the real value, not `"loop"`.
- [x] 1.2 Add `test_loop_with_trace_writer_plan_event_has_nonzero_seq`: same setup; assert the `kind="plan"` row has `seq >= 1`.
- [x] 1.3 Add `test_loop_with_trace_writer_plan_event_has_iso_ts`: same setup; assert the `kind="plan"` row's `ts` field is non-empty and parseable as ISO 8601.
- [x] 1.4 Add `test_loop_with_trace_writer_plan_event_seq_strictly_increasing`: run a loop with a `TraceWriter`; assert all `kind="plan"` rows have strictly increasing `seq` values and the first plan event has `seq >= 1`. Cross-kind ordering between plan and decision events is out of scope (tracked under `task2/plan.md` ticket #20 and ticket #26).
- [x] 1.5 Add `test_loop_with_trace_writer_replan_seq_after_initial_seq`: trigger a replan via supervisor halt with a `TraceWriter`; assert the `reason="replan"` plan event `seq` is strictly greater than the initial plan event `seq`.
- [x] 1.6 Add `test_loop_with_trace_writer_no_double_emit`: call `loop()` with both `trace_writer` and `events=[]`; assert the `events` list has no `PlanEvent` objects after the run.
- [x] 1.7 Add `test_loop_with_trace_writer_without_run_id_raises`: call `loop()` with a `TraceWriter` and no `run_id`; assert it raises `ValueError` with a message mentioning `run_id`.
- [x] 1.8 Run `uv run pytest task2/tests/agent/test_loop.py -k "trace_writer"` and confirm all new tests fail (red).

## 2. Type Fix

- [x] 2.1 In `task2/agent/loop.py`, change `_emit_plan_event`'s `reason` parameter type from `str` to `Literal["initial", "replan"]`.
- [x] 2.2 Remove the `# type: ignore[arg-type]` comment from the `PlanEvent(reason=reason, ...)` call inside `_emit_plan_event`.
- [x] 2.3 Run `uv run ruff check . && uv run ruff format .` from `task2/` and confirm exit 0.

## 3. Implementation (Green)

- [x] 3.1 Add `run_id: str | None = None` and `trace_writer: TraceWriter | None = None` keyword arguments to `loop()` in `task2/agent/loop.py`. Update the `TYPE_CHECKING` import block to include `TraceWriter` if not already present; add the runtime import.
- [x] 3.2 Add a local `_seq: int = 0` counter inside `loop()` that increments each time a plan event is written through the `TraceWriter`.
- [x] 3.3 Update `_emit_plan_event` to accept `trace_writer: TraceWriter | None`, `run_id: str | None`, and a `seq_ref` (or equivalent) so it can construct a `PlanEvent` with real metadata and call `trace_writer.append_event()`. When `trace_writer` is provided, do not append to `events`.
- [x] 3.4 Update both call-sites of `_emit_plan_event` in `loop()` (initial plan at step 1, replan at supervisor-halt boundary) to pass `trace_writer`, `run_id`, and the incremented seq.
- [x] 3.5 Add `from datetime import UTC, datetime` import to `loop.py` (if not already present) for ISO timestamp generation.
- [x] 3.6 At the top of `loop()`, raise `ValueError` when `trace_writer` is not `None` and `run_id` is `None` to prevent silent fallback to the in-memory `events` path.
- [x] 3.7 Run `uv run pytest task2/tests/agent/test_loop.py -k "trace_writer"` and confirm all new tests pass (green).
- [x] 3.8 Run `uv run pytest task2/tests/agent/test_loop.py` (full file) to confirm existing tests still pass (back-compat).

## 4. Wire Callers

- [x] 4.1 In `task2/api/server.py`, update the `_run_agent` function to pass `trace_writer=writer` and `run_id=run_id` to `loop()`. The `writer` is already created and `open_run` is called before `loop()` is invoked (via the `create_task` endpoint — verify the open_run call is visible to `_run_agent` or move it accordingly).
- [x] 4.2 If `eval/runner.py` exists and calls `loop()`, update it similarly to pass `trace_writer` and `run_id`.

## 5. Pre-commit Gate

- [x] 5.1 Run `uv run ruff format . && uv run ruff check . && uv run pytest` from `task2/` and confirm all exit 0.
- [x] 5.2 Commit with message `feat(task2): wire PlanEvent to TraceWriter in loop.py`.
