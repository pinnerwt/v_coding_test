# supervisor-event-emitter Specification

## Purpose
TBD - created by archiving change fix-mechanism-firings. Update Purpose after archive.

## Requirements

### Requirement: _emit_supervisor_event helper in loop.py

The system SHALL provide a private helper `_emit_supervisor_event` in `agent/loop.py` with the signature:

```python
def _emit_supervisor_event(
    *,
    trace_writer: TraceWriter | None,
    run_id: str | None,
    decision: EscalationDecision,
    miss: LocatorMiss,
    trigger_event_seq: int,
    step_id: str | None = None,
) -> None:
```

When `trace_writer` is `None` or `run_id` is `None`, the helper SHALL be a no-op (return immediately without side effects).

Otherwise, it SHALL:
1. Map `miss.reason` to `classified_as` using the following table: `"zero_matches"` → `"LocatorMiss"`, `"ambiguous"` → `"Ambiguous"`, `"vision_miss"` → `"LocatorMiss"`. Any unrecognised reason SHALL map to `"LocatorMiss"`.
2. Allocate a sequence number via `trace_writer.next_seq(run_id)`.
3. Construct a `SupervisorEvent` with `policy=decision.policy`, `attempt=decision.attempt`, `classified_as=<mapped value>`, `trigger_event_seq=trigger_event_seq`, `step_id=step_id`, and a valid ISO `ts`.
4. Call `trace_writer.append_event(event)`.

Because `EscalationDecision.policy` is now typed `EscalationPolicy` (the same `Literal` as `SupervisorEvent.policy`), the assignment `policy=decision.policy` SHALL be accepted by a static type checker without any `# type: ignore` comment. The `# type: ignore[arg-type]` suppression that previously appeared on that line SHALL be absent from the codebase.

#### Scenario: _emit_supervisor_event is a no-op when trace_writer is None

- **WHEN** `_emit_supervisor_event(trace_writer=None, run_id=None, decision=..., miss=..., trigger_event_seq=1, step_id=None)` is called
- **THEN** it SHALL return without raising and without writing any event

#### Scenario: _emit_supervisor_event writes SupervisorEvent with correct fields

- **GIVEN** an open `TraceWriter` with `run_id` and one prior event at seq=1
- **WHEN** `_emit_supervisor_event(trace_writer=writer, run_id=run_id, decision=EscalationDecision(next_tier="L2_dom", policy="next_tier", attempt=1), miss=LocatorMiss(reason="zero_matches", match_count=0), trigger_event_seq=1, step_id="r:step-2")` is called
- **THEN** the writer SHALL contain a new `SupervisorEvent` at seq=2
- **AND** `event.policy` SHALL equal `"next_tier"`
- **AND** `event.classified_as` SHALL equal `"LocatorMiss"`
- **AND** `event.trigger_event_seq` SHALL equal `1`
- **AND** `event.attempt` SHALL equal `1`
- **AND** `event.step_id` SHALL equal `"r:step-2"`

#### Scenario: _emit_supervisor_event maps ambiguous reason to Ambiguous

- **GIVEN** an open `TraceWriter` with `run_id`
- **WHEN** `_emit_supervisor_event(..., miss=LocatorMiss(reason="ambiguous", match_count=3), ...)` is called
- **THEN** the written `SupervisorEvent.classified_as` SHALL equal `"Ambiguous"`

#### Scenario: No type: ignore comment on policy assignment

- **WHEN** a static type checker (mypy or pyright) analyzes `agent/loop.py`
- **THEN** the line `policy=decision.policy` in `_emit_supervisor_event` SHALL produce no `arg-type` or equivalent suppression warning
- **AND** the source file SHALL contain no `# type: ignore[arg-type]` comment on that line

### Requirement: _locate_via_ladder emits LocateEvents for L1 miss and L2 outcomes

The private helper `_locate_via_ladder` in `agent/loop.py` SHALL be extended to accept three additional keyword arguments:

```python
def _locate_via_ladder(
    page: Page,
    intent: str,
    supervisor: Supervisor,
    *,
    trace_writer: TraceWriter | None = None,
    run_id: str | None = None,
    step_id: str | None = None,
) -> LocateResult:
```

When `trace_writer` and `run_id` are provided, the function SHALL:

1. After `locate_l1` raises `LocatorMiss(reason="zero_matches")`, emit a `LocateEvent(tier="L1_ax", outcome="miss", cache_action=None, intent=intent, chosen=None, candidates=[], ms=0, step_id=step_id)` using `_emit_locate_event`, and capture its allocated seq from the helper's return value as `l1_miss_seq`.
2. Call `supervisor.handle(miss, current_tier="L1_ax")` to obtain an `EscalationDecision`.
3. Call `_emit_supervisor_event(trace_writer=trace_writer, run_id=run_id, decision=decision, miss=miss, trigger_event_seq=l1_miss_seq, step_id=step_id)`.
4. If `decision.next_tier == "L2_dom"`: attempt `locate_l2`. If L2 succeeds, emit `LocateEvent(tier="L2_dom", outcome="hit", cache_action=None, intent=intent, chosen={"role": result.role, "selector": result.selector}, candidates=[], ms=0, step_id=step_id)`. If L2 raises `LocatorMiss`, emit `LocateEvent(tier="L2_dom", outcome="miss", cache_action=None, intent=intent, chosen=None, candidates=[], ms=0, step_id=step_id)` before re-raising.
5. If `decision.next_tier` is `None` (halt), re-raise the original L1 `LocatorMiss` (existing behavior unchanged).

When `trace_writer` is `None` or `run_id` is `None`, `_locate_via_ladder` SHALL behave identically to its current implementation (no emission, pure locate logic).

The existing callers of `_locate_via_ladder` (`_locate_with_supervisor`) SHALL be updated to forward `trace_writer`, `run_id`, and `step_id` when calling `_locate_via_ladder`.

#### Scenario: L1 miss emits LocateEvent before SupervisorEvent

- **GIVEN** an open `TraceWriter` with `run_id`, a page where `locate_l1` raises `LocatorMiss(reason="zero_matches")` and `locate_l2` succeeds
- **WHEN** `_locate_via_ladder(page, intent, supervisor, trace_writer=writer, run_id=run_id, step_id="r:step-1")` is called
- **THEN** the trace SHALL contain a `LocateEvent(tier="L1_ax", outcome="miss")` at the first new seq
- **AND** a `SupervisorEvent` at the next seq whose `trigger_event_seq` equals the L1 miss event's seq
- **AND** a `LocateEvent(tier="L2_dom", outcome="hit")` at the seq after the `SupervisorEvent`

#### Scenario: L2 miss emits LocateEvent and re-raises

- **GIVEN** an open `TraceWriter`, a page where both `locate_l1` and `locate_l2` raise `LocatorMiss`
- **WHEN** `_locate_via_ladder(page, intent, supervisor, trace_writer=writer, run_id=run_id, step_id=None)` is called
- **THEN** the trace SHALL contain a `LocateEvent(tier="L1_ax", outcome="miss")`, a `SupervisorEvent`, and a `LocateEvent(tier="L2_dom", outcome="miss")`
- **AND** `_locate_via_ladder` SHALL raise `LocatorMiss`

#### Scenario: No emission when trace_writer is None

- **GIVEN** a page where `locate_l1` raises and `locate_l2` succeeds, and no `TraceWriter` is provided
- **WHEN** `_locate_via_ladder(page, intent, supervisor)` is called (no trace kwargs)
- **THEN** the function SHALL return the L2 `LocateResult` with no errors
- **AND** no trace events SHALL be written

### Requirement: _locate_with_supervisor forwards trace kwargs to _locate_via_ladder

`_locate_with_supervisor` in `agent/loop.py` SHALL forward its `trace_writer`, `run_id`, and `step_id` arguments into the `_locate_via_ladder(page, intent, supervisor, ...)` call. This ensures L1/L2 trace events are emitted whether or not a `locator_cache` is provided.

#### Scenario: _locate_with_supervisor without cache threads trace kwargs into ladder

- **GIVEN** `_locate_with_supervisor(page, intent, supervisor, cache=None, trace_writer=writer, run_id=run_id, step_id="r:step-1")`
- **WHEN** `locate_l1` raises `LocatorMiss(reason="zero_matches")` and `locate_l2` succeeds
- **THEN** the `TraceWriter` SHALL contain a `LocateEvent(tier="L1_ax", outcome="miss")`, a `SupervisorEvent`, and a `LocateEvent(tier="L2_dom", outcome="hit")`

#### Scenario: _locate_with_supervisor with cache still emits ladder events on cache miss leading to ladder

- **GIVEN** `_locate_with_supervisor(page, intent, supervisor, cache=warm_cache_with_fingerprint_mismatch, trace_writer=writer, run_id=run_id, step_id="r:step-1")`
- **WHEN** the cache entry's AX fingerprint does not match the live element (triggering cache invalidation) and `_locate_via_ladder` is subsequently called
- **THEN** the trace SHALL contain a `LocateEvent(cache_action="invalidate")` from the cache path
- **AND** ALSO contain a `LocateEvent(tier="L1_ax", outcome="miss")` and/or a `SupervisorEvent` from the ladder path if L1 also misses on the post-invalidation fresh resolve
