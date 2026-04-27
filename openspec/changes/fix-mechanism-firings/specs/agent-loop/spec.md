## MODIFIED Requirements

### Requirement: loop function

The system SHALL provide `agent.loop.loop(task, browser, llm_client, *, max_steps=20, events=None, run_id=None, trace_writer=None, locator_cache=None)` — a synchronous function that drives the observe → decide → act cycle and returns a `RunResult` with all metric fields populated.

- `steps` SHALL equal the number of completed observe→decide→act iterations.
- `prompt_tokens`, `completion_tokens`, `usd` SHALL be cumulated from each `llm_client.chat()` call, **including the planner LLM call(s)**.
- `latency_ms_per_step` SHALL have one entry per step (wall time for the full observe→decide→dispatch cycle).
- `latency_ms_total` SHALL equal `sum(latency_ms_per_step)`.
- `step_breakdown[i]` SHALL have `step=i+1`, `latency_ms`, `prompt_tokens`, `completion_tokens`, `usd`, `tool_calls` (list of tool name strings called in that step).
- The loop SHALL call `agent.plan.plan()` once after the first observation and inject "Plan progress" into every subsequent decision user message.
- On supervisor `policy="halt"`, the loop SHALL trigger at most one `agent.plan.replan()` before returning `RunResult(status="failed")`.
- The new `locator_cache: LocatorCache | None = None` kwarg SHALL be accepted and, when not `None`, threaded as the cache argument into `_locate_with_supervisor` during `read` tool dispatch with a non-empty `intent`. When `None`, the loop SHALL not pass any cache to `_locate_with_supervisor` (current default behavior is preserved for all existing callers).
- When `locator_cache` is not `None` AND `trace_writer` and `run_id` are also provided, the loop SHALL emit a `LocateEvent` for each cache action taken inside `_locate_with_supervisor`:
  - `cache_action="read"` + `outcome="hit"` + `tier="cache"` when a cached entry's live fingerprint matches.
  - `cache_action="invalidate"` + `outcome="miss"` + `tier="cache"` whenever `cache.invalidate(...)` is called.
  - `cache_action="write"` + `outcome="hit"` + `tier=<resolved ladder tier>` whenever `cache.put(...)` is called after a fresh ladder resolve.
  - The loop SHALL NOT emit a `LocateEvent` when `locator_cache is None` or when the ladder resolves without any cache interaction.
- When `trace_writer` and `run_id` are provided (regardless of `locator_cache`), the loop SHALL emit trace events for locator ladder outcomes via `_locate_via_ladder`: a `LocateEvent(tier="L1_ax", outcome="miss")` when L1 raises `LocatorMiss(reason="zero_matches")`, a `SupervisorEvent` immediately after the supervisor decision, and a `LocateEvent(tier="L2_dom", outcome="hit"/"miss")` on the L2 attempt result. This applies whether or not a `locator_cache` is provided.

#### Scenario: loop returns RunResult

- **WHEN** `loop(task, browser, llm_client)` is called with a valid `Browser` and `LLMClient`
- **THEN** it SHALL return a `RunResult` instance

#### Scenario: loop is bounded by max_steps

- **WHEN** the LLM never calls `done` or `fail` within `max_steps` iterations
- **THEN** the loop SHALL return `RunResult(status="timeout", result=None, evidence=None)` with `steps == max_steps`

#### Scenario: Metrics are non-zero after a successful 2-step run

- **GIVEN** a mocked `LLMClient` that returns a `goto` tool call on step 1 (usage: 100 prompt, 10 completion, usd 0.00022) and `done` on step 2 (usage: 150 prompt, 20 completion, usd 0.00034)
- **WHEN** the loop completes
- **THEN** `result.steps` SHALL equal `2`
- **AND** `result.prompt_tokens` SHALL equal `250` (plus planner tokens; the fixture mock may return 0 for planner)
- **AND** `result.latency_ms_total` SHALL be positive

#### Scenario: locator_cache=None leaves existing callers unaffected

- **WHEN** `loop(task, browser, llm_client)` is called without the `locator_cache` argument (default `None`)
- **THEN** the loop SHALL behave identically to before this change: no cache is passed to `_locate_with_supervisor`, and no `LocateEvent` with `cache_action` is emitted for cache-related reasons

#### Scenario: Escalation trace events emitted on L1 miss with trace_writer provided

- **GIVEN** a `loop()` call with `trace_writer=writer`, `run_id=run_id`, and no `locator_cache`
- **AND** a scripted LLM that issues `read(intent="Submit button")` on step 1, which causes `locate_l1` to raise `LocatorMiss(reason="zero_matches")` and `locate_l2` to succeed
- **WHEN** the loop completes
- **THEN** `writer.iter_events(run_id)` SHALL yield a `LocateEvent(tier="L1_ax", outcome="miss")`
- **AND** a `SupervisorEvent(policy="next_tier", classified_as="LocatorMiss")` whose `trigger_event_seq` equals the L1 miss event's `seq`
- **AND** a `LocateEvent(tier="L2_dom", outcome="hit")`

#### Scenario: Integration — real loop on correction-l1-miss-l2-hit fixture produces non-zero escalations

- **GIVEN** the `correction_l1_miss.html` fixture page (contains `<div class="btn">Submit</div>` with no ARIA role)
- **AND** a real `loop()` call with a scripted LLM client (deterministic `ChatResponse` objects — `step 1: goto(fixture_url)`, `step 2: read(intent="Submit button")`, `step 3: done(...)`)
- **AND** a real `TraceWriter` (in-memory) and `run_id`
- **WHEN** `loop()` completes and `_aggregate_diagnostics(writer, run_id)` is called
- **THEN** `escalations` SHALL contain at least one entry
- **AND** that entry SHALL have `from_tier="L1_ax"` (L1 misses because the element has no accessible role) and `to_tier` set to `"L2_dom"` or `None` (L2 may or may not match, depending on fixture)
- **AND** this assertion SHALL fail if `_emit_supervisor_event` is removed from `_locate_via_ladder` (regression guard)
