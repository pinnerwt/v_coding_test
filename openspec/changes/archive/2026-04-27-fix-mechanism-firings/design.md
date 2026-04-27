## Context

The agent loop (`agent/loop.py`) calls `Supervisor.handle()` inside `_locate_via_ladder` (via `_locate_with_supervisor`) whenever a `LocatorMiss` is raised by `locate_l1`. The `Supervisor` returns an `EscalationDecision` that determines whether to try L2 or halt. This decision is used by `loop.py` to drive behavior — but it is **never written to the `TraceWriter`**.

`scripts/eval.py:_aggregate_diagnostics` reads `SupervisorEvent` rows from the trace to populate `CaseResult.escalations`. Because no `SupervisorEvent` is ever emitted, `escalations` is always `[]`, `replans=0`, and `cache_events={}` in every live run. The unit tests in `test_eval.py` pass because they mock `loop()` to emit the events directly — bypassing the real emission gap entirely.

The same gap applies to L1/L2 ladder `LocateEvent` emission: `_locate_via_ladder` calls `locate_l1` and (on miss) `locate_l2`, but never emits `LocateEvent` rows for these ladder outcomes. Only the cache-path branches inside `_locate_with_supervisor` emit `LocateEvent`. This means `_aggregate_diagnostics` has no `trigger_event_seq` anchor for the `SupervisorEvent` it needs to correlate escalation entries.

A secondary concern is verifying that ticket #28's `locator_cache` forwarding (`_run_case` → `loop()`) actually reaches `_locate_with_supervisor` with a non-`None` cache in production runs — this is required for the cache invalidation path to fire on `maintenance-drift-rename-v2`.

## Goals / Non-Goals

**Goals:**
- Emit `LocateEvent(tier="L1_ax", outcome="miss")` inside `_locate_via_ladder` before escalating to L2, and `LocateEvent(tier="L2_dom", outcome="hit"/"miss")` on L2 outcome.
- Emit `SupervisorEvent` inside `_locate_with_supervisor` after every `Supervisor.handle()` call, setting `trigger_event_seq` to the seq of the immediately preceding L1 `LocateEvent` for the same intent.
- Add a helper `_emit_supervisor_event` in `loop.py` alongside the existing `_emit_locate_event`.
- Thread `trace_writer`, `run_id`, and `step_id` into `_locate_via_ladder` so it can emit.
- Add an integration test (Playwright + real `loop()`) for at least one of `correction-l1-miss-l2-hit` / `correction-replan` / `maintenance-drift-rename-v2` that asserts non-zero mechanism firing via `_aggregate_diagnostics`.
- All existing unit tests continue to pass with no changes required.

**Non-Goals:**
- No change to `Supervisor.handle()` logic or the escalation table.
- No change to `scripts/eval.py` or `_aggregate_diagnostics`.
- No change to `agent/trace.py` schema.
- No change to L3 or L4 locate paths (they are not yet wired into `_locate_via_ladder`).
- No LLM provider changes or hardcoded URLs.
- No fix to the failing case outcomes themselves (the 6/8 failures that are separate from firing rates).

## Decisions

### Decision 1: Emit L1/L2 LocateEvents inside `_locate_via_ladder`, not inside `locate_l1`/`locate_l2`

**Chosen**: Thread `trace_writer`, `run_id`, `step_id` into `_locate_via_ladder` and call `_emit_locate_event` at each outcome point inside that function. Do NOT add emission to `locate_l1` or `locate_l2` themselves.

**Rationale**: `locate_l1` and `locate_l2` are pure locate functions with no trace dependency. Adding `trace_writer` to their signatures would couple the core locator API to the trace infrastructure and break every existing test that calls them directly. `_locate_via_ladder` is already a private `loop.py` helper — adding kwargs there is a local change with zero external API impact.

**Alternative rejected**: Passing `trace_writer` into `locate_l1`/`locate_l2` via optional kwargs — rejected because it pollutes the locator public API and makes future callers (e.g., L3/L4 integration) harder to reason about.

### Decision 2: Emit `SupervisorEvent` inside `_locate_with_supervisor`, immediately after `Supervisor.handle()` returns

**Chosen**: Add a call to `_emit_supervisor_event(...)` inside `_locate_with_supervisor`, right after `decision = supervisor.handle(miss, current_tier="L1_ax")`. The `trigger_event_seq` is set to the seq of the L1 miss `LocateEvent` emitted by `_locate_via_ladder` in the call that just returned.

**Rationale**: `_locate_with_supervisor` is the single call site where `supervisor.handle()` is invoked. Placing emission here keeps the logic co-located with the decision point. `_emit_locate_event` returns the seq it allocated, so the L1 miss event's seq is captured directly from that return value and passed as `trigger_event_seq` — no reliance on `next_seq` arithmetic.

**Alternative rejected**: Emitting the `SupervisorEvent` inside `_locate_via_ladder` — rejected because `_locate_via_ladder` doesn't hold a `Supervisor` reference and would require more parameter threading.

### Decision 3: `classified_as` mapping from `miss.reason`

**Chosen**: Map `miss.reason` → `classified_as` as follows: `"zero_matches"` → `"LocatorMiss"`, `"ambiguous"` → `"Ambiguous"`, `"vision_miss"` → `"LocatorMiss"`. These are the only `LocatorMissReason` values and they map to the two most applicable `classified_as` literals in `SupervisorEvent`.

**Rationale**: `SupervisorEvent.classified_as` is typed as `Literal["LocatorMiss", "Ambiguous", "NoEffect", "FormError", "NavDrift", "Blocked", "Timeout"]`. The supervisor-escalation spec uses `"LocatorMiss"` for zero_matches escalation, which is the only path exercised today.

### Decision 4: Integration test approach

**Chosen**: Add a new test in `tests/test_loop.py` (not `test_eval.py`) that uses Playwright `sync_api` to serve the `correction_l1_miss.html` fixture via a local HTTP server (or `page.set_content()`), runs the real `loop()` with a scripted LLM client (deterministic responses via `unittest.mock`), and asserts `escalations` is non-empty after `_aggregate_diagnostics`.

**Rationale**: The done-bar says "a test that runs the real loop (not just the mock) asserts it." Using a scripted (not mocked-at-class-level) LLM — i.e., a `MagicMock` whose `chat()` returns pre-baked `ChatResponse` objects with correct structure — is sufficient. The test exercises the real `locate_l1` → `LocatorMiss` → `Supervisor.handle()` → `_emit_supervisor_event` path without requiring a live Qwen instance.

**Alternative rejected**: Running against the real Qwen 27B — rejected because it is non-deterministic, slow, and unavailable in CI. The ticket says "real (or scripted) Qwen client."

## Risks / Trade-offs

- **seq calculation for `trigger_event_seq`**: Using `next_seq - 1` would be fragile if any other code emitted an event between the L1 `LocateEvent` and the `SupervisorEvent`. Resolution: `_emit_locate_event` returns the allocated `seq` directly, and `_locate_via_ladder` captures that return value to pass as `trigger_event_seq`. No `next_seq - 1` arithmetic is used, so the invariant is enforced by the call structure rather than by a comment.
- **Integration test flakiness via Playwright**: Using `page.set_content()` avoids a local HTTP server, which is simpler and more portable. Mitigation: use `page.set_content()` so the test never depends on a network port.
- **L2-miss emission landed:** `_locate_via_ladder` emits a `LocateEvent(tier="L2_dom", outcome="miss")` before re-raising on L2 failure; covered by `test_locate_via_ladder_l1_miss_l2_miss_emits_events_and_raises`. The original risk that this path was untested is resolved.

## Open Questions

None — all three suspects from the ticket have been diagnosed:
- (a) Confirmed: `loop()` does call the escalation path via `_locate_via_ladder`, but never emits trace events.
- (b) `SupervisorEvent.policy` would be `"next_tier"` for L1→L2 escalation — but no event is emitted, so the field value is moot.
- (c) Cache `invalidate` path: ticket #28 did land (the `locator_cache` kwarg is in `loop()`'s signature and forwarded in `_run_case`). The invalidation `LocateEvent` emission is already present in `_locate_with_supervisor`. The gap is that L1 miss never emits a `LocateEvent`, so `_aggregate_diagnostics` has no `trigger_event_seq` to correlate with the missing `SupervisorEvent`.
