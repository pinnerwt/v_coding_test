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
- The new `locator_cache: LocatorCache | None = None` kwarg SHALL be accepted and, when not `None`, threaded into every `locate()` call made during `read` tool dispatch with a non-empty `intent`. When `None`, the loop SHALL not pass any cache to `locate()` (current default behavior is preserved for all existing callers).

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
- **THEN** the loop SHALL behave identically to before this change: no cache is passed to `locate()` calls, and no `LocateEvent` with `cache_action` is emitted for cache-related reasons

#### Scenario: locator_cache is threaded into read dispatch when provided

- **GIVEN** a shared `LocatorCache` instance `cache` passed as `locator_cache=cache` to `loop()`
- **AND** the LLM emits a `read(intent="Submit button")` tool call
- **WHEN** the loop dispatches that tool call
- **THEN** `agent.locate.locate(page, "Submit button", cache=cache)` SHALL be called (the cache object is forwarded)

#### Scenario: Cache hit from v1 is invalidated when loop runs on v2 page

- **GIVEN** a shared `LocatorCache` that was warmed during a prior loop run on a v1 fixture page (e.g. `drift/rename/v1/index.html` — button with accessible name "Submit")
- **AND** `loop()` is called with that same cache on a v2 fixture page (`drift/rename/v2/index.html` — button with accessible name "Send")
- **AND** the LLM emits `read(intent="Submit button")`
- **WHEN** the locate call probes the cache
- **THEN** the fingerprint mismatch SHALL cause `cache.invalidate()` to be called
- **AND** the trace for this run SHALL contain a `LocateEvent(cache_action="invalidate")`
- **AND** `_aggregate_diagnostics(writer, run_id)["cache_events"]["invalidations"]` SHALL be `>= 1`

## ADDED Requirements

### Requirement: locator_cache kwarg accepted by loop with None default

`agent.loop.loop()` SHALL accept `locator_cache: LocatorCache | None = None` as a keyword-only argument. The parameter SHALL appear in the function signature after `trace_writer`. Its default value SHALL be `None`. All existing call sites that do not pass `locator_cache` SHALL continue to work without modification.

#### Scenario: Existing call sites do not require update

- **GIVEN** any existing call to `loop(task, browser, llm_client)` or `loop(task, browser, llm_client, max_steps=N)` or `loop(task, browser, llm_client, trace_writer=w, run_id=r)`
- **WHEN** the new `locator_cache` parameter is added with `None` default
- **THEN** none of those call sites SHALL require a change to continue functioning correctly
