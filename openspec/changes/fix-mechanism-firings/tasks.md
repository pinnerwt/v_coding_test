## 1. Red — Failing integration test

- [x] 1.1 Add `test_real_loop_correction_l1_miss_produces_escalation` in `task2/tests/test_loop.py`: spin up a Playwright `Browser` pointing at `tests/fixtures/correction_l1_miss.html` via `page.set_content()`, construct a scripted `LLMClient` mock whose `chat()` returns pre-baked `ChatResponse` objects (`step 1: goto(fixture_url)`, `step 2: read(intent="Submit button")`, `step 3: done(...)`), call real `loop()` with a real in-memory `TraceWriter`, then assert `_aggregate_diagnostics(writer, run_id).escalations` is non-empty. Confirm the test is RED before any production code changes.
- [x] 1.2 Run `uv run pytest task2/tests/test_loop.py::test_real_loop_correction_l1_miss_produces_escalation -x` and capture the failure — expected: `assert len(escalations) >= 1` fails because `escalations == []`.

## 2. Add `_emit_supervisor_event` helper in `agent/loop.py`

- [x] 2.1 Import `SupervisorEvent` from `agent.trace` and `EscalationDecision` from `agent.supervisor` at the top of `agent/loop.py` (add to existing imports).
- [x] 2.2 Write `_emit_supervisor_event(*, trace_writer, run_id, decision, miss, trigger_event_seq, step_id=None)` following the spec: no-op when `trace_writer is None` or `run_id is None`; otherwise map `miss.reason` → `classified_as`, allocate seq via `next_seq`, construct and append `SupervisorEvent`.
- [x] 2.3 Add unit tests in `task2/tests/test_loop.py` for `_emit_supervisor_event`: (a) no-op when `trace_writer=None`; (b) writes `SupervisorEvent` with correct `policy`, `classified_as`, `trigger_event_seq`, `attempt`, `step_id`; (c) maps `"ambiguous"` → `"Ambiguous"`.

## 3. Extend `_locate_via_ladder` to emit LocateEvents and call `_emit_supervisor_event`

- [x] 3.1 Add `trace_writer: TraceWriter | None = None`, `run_id: str | None = None`, `step_id: str | None = None` keyword arguments to `_locate_via_ladder` in `agent/loop.py`.
- [x] 3.2 Inside `_locate_via_ladder`, after `locate_l1` raises `LocatorMiss(reason="zero_matches")`: call `_emit_locate_event(trace_writer=trace_writer, run_id=run_id, intent=intent, tier="L1_ax", outcome="miss", cache_action=None, chosen=None, step_id=step_id)` and capture `l1_seq = (trace_writer.next_seq(run_id) - 1)` immediately (or snapshot seq before emission using `next_seq - 1` after the emit).
- [x] 3.3 After computing `decision = supervisor.handle(miss, current_tier="L1_ax")`, call `_emit_supervisor_event(trace_writer=trace_writer, run_id=run_id, decision=decision, miss=miss, trigger_event_seq=l1_seq, step_id=step_id)`.
- [x] 3.4 If `decision.next_tier == "L2_dom"` and `locate_l2` succeeds: emit `LocateEvent(tier="L2_dom", outcome="hit", cache_action=None, chosen={"role": result.role, "selector": result.selector}, ...)`.
- [x] 3.5 If `decision.next_tier == "L2_dom"` and `locate_l2` raises `LocatorMiss`: emit `LocateEvent(tier="L2_dom", outcome="miss", cache_action=None, chosen=None, ...)` before re-raising.
- [x] 3.6 Add unit tests for `_locate_via_ladder` with trace kwargs: (a) L1 miss → L2 hit produces three events in correct order with correct `trigger_event_seq` correlation; (b) L1 miss → L2 miss produces three events and re-raises; (c) no trace kwargs → no events emitted, same return value as before.

## 4. Thread trace kwargs from `_locate_with_supervisor` into `_locate_via_ladder`

- [x] 4.1 In `_locate_with_supervisor`, update the `_locate_via_ladder(page, intent, supervisor)` call to `_locate_via_ladder(page, intent, supervisor, trace_writer=trace_writer, run_id=run_id, step_id=step_id)`.
- [x] 4.2 Run `uv run pytest task2/tests/ -x` and confirm all pre-existing tests still pass.

## 5. Green — Integration test passes

- [x] 5.1 Re-run `uv run pytest task2/tests/test_loop.py::test_real_loop_correction_l1_miss_produces_escalation -x` and confirm it is now GREEN.
- [x] 5.2 Run the full test suite: `uv run pytest task2/tests/ -x` — all tests must pass.

## 6. Linter and format

- [x] 6.1 Run `uv run ruff check task2/agent/loop.py task2/tests/test_loop.py` and fix any issues.
- [x] 6.2 Run `uv run ruff format task2/agent/loop.py task2/tests/test_loop.py` to normalise formatting.
- [x] 6.3 Re-run `uv run pytest task2/tests/ -x` to confirm tests still pass after formatting.

## 7. Smoke-check benchmark results

- [x] 7.1 Run `uv run python -m scripts.eval --case correction-l1-miss-l2-hit` from `task2/` against the local Qwen instance (or scripted stub) and confirm `escalations` is non-empty in the output JSON. If Qwen is unavailable, this step is advisory — the integration test (step 5.1) is the binding done-bar. **Deferred** — local Qwen serves `qwen3.5-27b` but eval runner default `LLM_MODEL=qwen3` 404s; pre-existing infra mismatch unrelated to this change. Binding done-bar (5.1) is GREEN.
