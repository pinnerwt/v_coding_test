## Why

The live benchmark shows 0/8 mechanism-firing rates for escalations, replans, and cache invalidations across all diagnostic cases — even `correction-l1-miss-l2-hit`, `correction-replan`, and `maintenance-drift-rename-v2`, which were introduced in ticket #27 precisely to prove those mechanisms fire. The root cause is that `agent/loop.py` and `agent/supervisor.py` never write `SupervisorEvent` rows to the `TraceWriter`, so `_aggregate_diagnostics` in `scripts/eval.py` finds no `SupervisorEvent` entries to aggregate. Additionally, ticket #28's `locator_cache` forwarding from `_run_case` into `loop()` was implemented, but a secondary gap remains: `_locate_via_ladder` (the fallback used by `_locate_with_supervisor` when no cache is provided) never emits any trace events at all, meaning the escalation path taken by the real loop is invisible to the eval runner. These two missing event emissions are the sole reason the scoreboard shows all zeros.

## What Changes

- **Emit `SupervisorEvent` on every `Supervisor.handle()` call inside `_locate_with_supervisor`** — when `trace_writer` and `run_id` are provided, write a `SupervisorEvent` row capturing `policy`, `classified_as` (mapped from `miss.reason`), `attempt`, and `trigger_event_seq` (seq of the immediately preceding `LocateEvent` for the same intent).
- **Emit `LocateEvent` on L1 miss inside `_locate_via_ladder`** — currently only `_locate_with_supervisor`'s cache-path branches emit `LocateEvent`; the ladder fallback (`locate_l1` / `locate_l2`) emits nothing. Add a `LocateEvent(tier="L1_ax", outcome="miss")` before escalating, and a `LocateEvent(tier="L2_dom", outcome="hit")` on success, so `_aggregate_diagnostics` has the `trigger_event_seq` anchor it needs.
- **Add an integration test that runs the real `loop()` (not a mock)** against the fixture HTMLs for at least one of the three diagnostic cases and asserts non-zero firing in the aggregated `CaseResult`. This is the done-bar test the ticket specifies.
- **Verify `locator_cache` forwarding landed end-to-end** (ticket #28 clause): confirm the `maintenance-drift-rename-v2` path actually reaches `_locate_with_supervisor` with a non-`None` cache and that the invalidation `LocateEvent` is reachable under real conditions.

## Capabilities

### New Capabilities

- `supervisor-event-emitter`: Specifies that `_locate_with_supervisor` emits a `SupervisorEvent` to the `TraceWriter` on every `Supervisor.handle()` call, and that `_locate_via_ladder` emits `LocateEvent` rows for L1 miss and L2 hit outcomes when a `trace_writer` is threaded through.

### Modified Capabilities

- `agent-loop`: The `_locate_via_ladder` helper (called from `_locate_with_supervisor`) must accept and thread `trace_writer`, `run_id`, and `step_id` kwargs so it can emit `LocateEvent` rows. The existing `_locate_with_supervisor` signature is extended to call a new `_emit_supervisor_event` helper. All existing `LocateEvent` emission contracts are unchanged; this adds new ones.
- `eval-proof-metrics`: The done-bar requirement (at least one of the three diagnostic cases shows non-zero firings on a real loop run) needs a new integration-level scenario that uses the real `loop()` rather than a mocked one.

## Impact

- `task2/agent/loop.py` — `_locate_via_ladder`, `_locate_with_supervisor`, and a new `_emit_supervisor_event` helper.
- `task2/agent/supervisor.py` — no change to `Supervisor.handle()` itself; only the call site in `loop.py` gains emission.
- `task2/agent/trace.py` — no change; `SupervisorEvent` already exists in the schema.
- `task2/scripts/eval.py` — no change; `_aggregate_diagnostics` already reads `SupervisorEvent` rows.
- `task2/tests/test_eval.py` — add integration test(s) that spin up a real `loop()` + `Browser` against local fixture HTML.
- `task2/tests/test_loop.py` — add unit tests for `_emit_supervisor_event` and the new `LocateEvent` emission inside `_locate_via_ladder`.
