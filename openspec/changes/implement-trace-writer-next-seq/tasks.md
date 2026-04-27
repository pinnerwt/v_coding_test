## 1. Failing Tests — TraceWriter.next_seq (Red)

- [x] 1.1 In `task2/tests/agent/test_trace.py`, add `test_next_seq_on_fresh_run_returns_1`: open a run with no events; assert `writer.next_seq(run_id)` returns `1`.
- [x] 1.2 Add `test_next_seq_after_one_event_returns_2`: append one event at seq=1; assert `next_seq(run_id)` returns `2`.
- [x] 1.3 Add `test_next_seq_after_three_events_returns_4`: append three events at seq=1,2,3; assert `next_seq(run_id)` returns `4`.
- [x] 1.4 Add `test_next_seq_unknown_run_id_raises`: call `next_seq("does-not-exist")` on a writer with no runs; assert `LookupError` is raised.
- [x] 1.5 Add `test_next_seq_closed_run_raises`: open and close a run via `close_run`; assert `next_seq(run_id)` raises `LookupError`.
- [x] 1.6 Run `uv run pytest task2/tests/agent/test_trace.py -k "next_seq"` and confirm all new tests fail (red).

## 2. Failing Test — Interleaved Emitters (Red)

- [x] 2.1 In `task2/tests/agent/test_loop.py`, add `test_interleaved_emitters_no_seq_error`: call `loop()` with a `:memory:` `TraceWriter` and mocks that cause the loop to emit one initial `PlanEvent` and then terminate (done tool); after `loop()` returns, append a manually-constructed `ObservationEvent` using `seq=writer.next_seq(run_id)`; assert both rows exist in `traces_events` with strictly increasing seq and no `SeqError` was raised.
- [x] 2.2 Run `uv run pytest task2/tests/agent/test_loop.py -k "interleaved"` and confirm the test fails (red — `next_seq` does not exist yet).

## 3. Implementation — TraceWriter.next_seq (Green)

- [x] 3.1 In `task2/agent/trace.py`, add a `_NEXT_SEQ_SQL` constant: `"SELECT status, (SELECT MAX(seq) FROM traces_events WHERE run_id = r.run_id) FROM traces_runs r WHERE r.run_id = ?"`. **Divergence: reused existing `_RUN_STATE_SQL` (identical query) instead of adding a duplicate constant. No new constant needed.**
- [x] 3.2 Add `next_seq(self, run_id: str) -> int` to `TraceWriter`: execute `_RUN_STATE_SQL`, raise `LookupError` (via `_missing_run`) if no row, raise `LookupError` (via `_closed_run`) if `status` is not `None`, return `(max_seq or 0) + 1`.
- [x] 3.3 Run `uv run pytest task2/tests/agent/test_trace.py -k "next_seq"` and confirm all `next_seq` tests pass (green).
- [x] 3.4 Run `uv run pytest task2/tests/agent/test_trace.py` (full file) and confirm no regressions.

## 4. Implementation — Remove plan_seq from loop.py (Green)

- [ ] 4.1 In `task2/agent/loop.py`, remove the `seq: int = 0` parameter from `_emit_plan_event`'s signature.
- [ ] 4.2 In `_emit_plan_event`, replace `seq=seq if use_writer else 0` with `seq=trace_writer.next_seq(run_id) if use_writer else 0`. The `next_seq` call must happen before the `PlanEvent(...)` constructor so the seq is captured at emit time.
- [ ] 4.3 Remove the `plan_seq: int = 0` local variable from `loop()`.
- [ ] 4.4 Remove the two `plan_seq += 1` lines from `loop()` (one before the initial plan emit, one before the replan emit).
- [ ] 4.5 Update both `_emit_plan_event(...)` call-sites in `loop()` to remove the `seq=plan_seq` argument.
- [ ] 4.6 Run `uv run pytest task2/tests/agent/test_loop.py -k "interleaved"` and confirm the interleaved test passes (green).
- [ ] 4.7 Run `uv run pytest task2/tests/agent/test_loop.py` (full file) and confirm all existing tests still pass (back-compat).

## 5. Pre-commit Gate

- [ ] 5.1 Run `uv run ruff format . && uv run ruff check .` from `task2/` and confirm exit 0.
- [ ] 5.2 Run `uv run pytest` from `task2/` (full suite) and confirm exit 0.
- [ ] 5.3 Commit with message `feat(task2): add TraceWriter.next_seq and remove plan_seq counter from loop.py`.
