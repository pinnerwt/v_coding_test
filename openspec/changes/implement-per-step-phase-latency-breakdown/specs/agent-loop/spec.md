## ADDED Requirements

### Requirement: Per-step phase latency breakdown

The system SHALL capture three monotonic timestamps inside each iteration of `loop()` and write them under a `latency_breakdown_ms` key in every `step_breakdown` entry.

- `t_obs_start` SHALL be captured immediately before `observe.build_observation(...)` is called.
- `t_llm_start` SHALL be captured immediately before `llm_client.chat(...)` is called.
- `t_dispatch_start` SHALL be captured immediately before the `for tool_call in response.tool_calls:` loop begins (or, when no tool calls are present, immediately before the no-tool-call branch is evaluated).
- `observation_ms` SHALL equal `int((t_llm_start - t_obs_start) * 1000)`.
- `llm_ms` SHALL equal `int((t_dispatch_start - t_llm_start) * 1000)`.
- `dispatch_ms` SHALL equal `int((time.monotonic() - t_dispatch_start) * 1000)` computed at the `_record_step` call site.
- The `latency_breakdown_ms` dict written into `step_breakdown[i]` SHALL have exactly the keys `observation_ms`, `llm_ms`, and `dispatch_ms`, all integers.
- The dict SHALL be present on every `step_breakdown` entry regardless of how the step exits (no-tool-call, `done`, `fail`, `stuck_repeat`, replan-exhaustion, max-steps). No entry SHALL have a missing or `null` `latency_breakdown_ms`.
- Sum invariant: `abs((observation_ms + llm_ms + dispatch_ms) - latency_ms) <= 5` SHALL hold for every step in a run, allowing ±5 ms for bookkeeping overhead between `t0` and `t_obs_start`.

#### Scenario: Phase ranges match stub sleep durations

- **GIVEN** a stub `LLMClient` whose `chat()` sleeps 0.4 s before returning
- **AND** a stub `Browser` whose `build_observation()` sleeps 0.1 s before returning
- **AND** the stub LLM returns a `done` tool call so the run completes in one step
- **WHEN** `loop(task, browser, llm_client)` is called
- **THEN** `step_breakdown[0]["latency_breakdown_ms"]["llm_ms"]` SHALL be in the range `[350, 600]`
- **AND** `step_breakdown[0]["latency_breakdown_ms"]["observation_ms"]` SHALL be in the range `[80, 200]`

#### Scenario: Sum invariant holds across all steps in a 5-step run

- **GIVEN** a stub `LLMClient` that returns `goto` on steps 1–4 and `done` on step 5
- **WHEN** `loop(task, browser, llm_client)` runs to completion
- **THEN** for every entry `s` in `result.step_breakdown`, `abs((s["latency_breakdown_ms"]["observation_ms"] + s["latency_breakdown_ms"]["llm_ms"] + s["latency_breakdown_ms"]["dispatch_ms"]) - s["latency_ms"]) <= 5` SHALL hold

#### Scenario: latency_breakdown_ms present on all entries including no-tool-call steps

- **GIVEN** a stub `LLMClient` that returns no tool calls for two steps then `done` on step 3
- **WHEN** `loop(task, browser, llm_client)` is called
- **THEN** every entry in `result.step_breakdown` SHALL have a `latency_breakdown_ms` key
- **AND** each `latency_breakdown_ms` SHALL contain exactly the keys `observation_ms`, `llm_ms`, and `dispatch_ms`
- **AND** none of those values SHALL be `None`

## MODIFIED Requirements

### Requirement: loop function

The system SHALL provide `agent.loop.loop(task, browser, llm_client, *, max_steps=20, events=None, run_id=None, trace_writer=None, locator_cache=None, expect=None, budget_seconds=None)` — a synchronous function that drives the observe → decide → act cycle and returns a `RunResult` with all metric fields populated.

- `steps` SHALL equal the number of completed observe→decide→act iterations.
- `prompt_tokens`, `completion_tokens`, `usd` SHALL be cumulated from each `llm_client.chat()` call, **including the planner LLM call(s)**.
- `latency_ms_per_step` SHALL have one entry per step (wall time for the full observe→decide→dispatch cycle).
- `latency_ms_total` SHALL equal `sum(latency_ms_per_step)`.
- `step_breakdown[i]` SHALL have `step=i+1`, `latency_ms`, `prompt_tokens`, `completion_tokens`, `usd`, `tool_calls` (list of tool name strings called in that step), and `latency_breakdown_ms` (a dict with integer keys `observation_ms`, `llm_ms`, `dispatch_ms` — see the `Per-step phase latency breakdown` requirement).
- The loop SHALL call `agent.plan.plan()` once after the first observation and inject "Plan progress" into every subsequent decision user message.
- On supervisor `policy="halt"`, the loop SHALL trigger at most one `agent.plan.replan()` before returning `RunResult(status="failed")`.
- The new `locator_cache: LocatorCache | None = None` kwarg SHALL be accepted and, when not `None`, threaded as the cache argument into `_locate_with_supervisor` during `read` tool dispatch with a non-empty `intent`. When `None`, the loop SHALL not pass any cache to `_locate_with_supervisor` (current default behavior is preserved for all existing callers).
- When `locator_cache` is not `None` AND `trace_writer` and `run_id` are also provided, the loop SHALL emit a `LocateEvent` for each cache action taken inside `_locate_with_supervisor`:
  - `cache_action="read"` + `outcome="hit"` + `tier="cache"` when a cached entry's live fingerprint matches.
  - `cache_action="invalidate"` + `outcome="miss"` + `tier="cache"` whenever `cache.invalidate(...)` is called.
  - `cache_action="write"` + `outcome="hit"` + `tier=<resolved ladder tier>` whenever `cache.put(...)` is called after a fresh ladder resolve.
  - The loop SHALL NOT emit a `LocateEvent` when `locator_cache is None` or when the ladder resolves without any cache interaction.
- When `trace_writer` and `run_id` are provided (regardless of `locator_cache`), the loop SHALL emit trace events for locator ladder outcomes via `_locate_via_ladder`: a `LocateEvent(tier="L1_ax", outcome="miss")` when L1 raises `LocatorMiss(reason="zero_matches")`, a `SupervisorEvent` immediately after the supervisor decision, and a `LocateEvent(tier="L2_dom", outcome="hit"/"miss")` on the L2 attempt result. This applies whenever the ladder is actually reached; when a `locator_cache` is provided and a fresh fingerprint match short-circuits the ladder, no L1/L2 ladder events are emitted for that step.
- The new `expect: dict | None = None` kwarg SHALL be accepted and forwarded as `expect=expect` into `_build_system_prompt(task, expect=expect)` when building the initial system message. When `None` (the default), `_build_system_prompt` receives no `expect` argument and behaves identically to before this change.
- The new `budget_seconds: float | None = None` kwarg SHALL be accepted; when not `None`, the loop SHALL terminate with `RunResult(status="timeout", reason="seconds_budget", ...)` as soon as monotonic wall-clock elapsed since loop entry meets or exceeds `budget_seconds`, checked at the top of each iteration before any other work. When `None`, no wall-clock check is performed.

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

#### Scenario: locator_cache is threaded into read dispatch when provided

- **GIVEN** a shared `LocatorCache` instance `cache` passed as `locator_cache=cache` to `loop()`
- **AND** the LLM emits a `read(intent="Submit button")` tool call
- **WHEN** the loop dispatches that tool call
- **THEN** `_locate_with_supervisor(page, "Submit button", supervisor, cache=cache, ...)` SHALL be called with the cache forwarded as the cache keyword argument

#### Scenario: Cache hit from v1 is invalidated when loop runs on v2 page

- **GIVEN** a shared `LocatorCache` that was warmed during a prior loop run on a v1 fixture page (e.g. `drift/rename/v1/index.html` — button with accessible name "Submit")
- **AND** `loop()` is called with that same cache on a v2 fixture page (`drift/rename/v2/index.html` — button with accessible name "Send")
- **AND** the LLM emits `read(intent="Submit button")`
- **WHEN** the locate call probes the cache
- **THEN** the fingerprint mismatch SHALL cause `cache.invalidate()` to be called
- **AND** the trace for this run SHALL contain a `LocateEvent(cache_action="invalidate")`
- **AND** `_aggregate_diagnostics(writer, run_id)["cache_events"]["invalidations"]` SHALL be `>= 1`

#### Scenario: Escalation trace events emitted on L1 miss with trace_writer provided

- **GIVEN** a `loop()` call with `trace_writer=writer`, `run_id=run_id`, and no `locator_cache`
- **AND** a scripted LLM that issues `read(intent="Submit button")` on step 1, which causes `locate_l1` to raise `LocatorMiss(reason="zero_matches")` and `locate_l2` to succeed
- **WHEN** the loop completes
- **THEN** `writer.iter_events(run_id)` SHALL yield a `LocateEvent(tier="L1_ax", outcome="miss")`
- **AND** a `SupervisorEvent(policy="next_tier", classified_as="LocatorMiss")` whose `trigger_event_seq` equals the L1 miss event's `seq`

#### Scenario: signature exposes latency_breakdown_ms via _record_step

- **WHEN** `_record_step` is called from any exit path inside `loop()`
- **THEN** the resulting `step_breakdown` entry SHALL contain `latency_breakdown_ms` with keys `observation_ms`, `llm_ms`, and `dispatch_ms` as integers
