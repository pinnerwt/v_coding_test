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

## ADDED Requirements

### Requirement: locator_cache kwarg accepted by loop with None default

`agent.loop.loop()` SHALL accept `locator_cache: LocatorCache | None = None` as a keyword-only argument. The parameter SHALL appear in the function signature after `trace_writer`. Its default value SHALL be `None`. All existing call sites that do not pass `locator_cache` SHALL continue to work without modification.

#### Scenario: Existing call sites do not require update

- **GIVEN** any existing call to `loop(task, browser, llm_client)` or `loop(task, browser, llm_client, max_steps=N)` or `loop(task, browser, llm_client, trace_writer=w, run_id=r)`
- **WHEN** the new `locator_cache` parameter is added with `None` default
- **THEN** none of those call sites SHALL require a change to continue functioning correctly

### Requirement: LocateEvent emission on cache actions

When `loop()` is called with `locator_cache` AND `trace_writer` AND `run_id`, the loop SHALL emit exactly one `LocateEvent` per cache action taken inside `_locate_with_supervisor`. Emission SHALL use a strictly-increasing `seq` allocated via `trace_writer.next_seq(run_id)` and SHALL populate `intent`, `tier`, `outcome`, `cache_action`, and `chosen` according to the action taken.

#### Scenario: Write event emitted on first resolve into an empty cache

- **GIVEN** an empty `LocatorCache` and a `TraceWriter` open on `run_id`
- **AND** the LLM emits `read(intent="Submit button")` for a v1 fixture page
- **WHEN** the locate call resolves through the L1/L2 ladder and writes to the cache
- **THEN** exactly one `LocateEvent` row SHALL be appended with `cache_action="write"`, `outcome="hit"`, `intent="Submit button"`, and `tier` equal to the ladder tier that resolved the element

#### Scenario: Invalidate event emitted before write on drift

- **GIVEN** a shared `LocatorCache` warmed from a v1 run
- **AND** a fresh `TraceWriter` and `run_id` for a second run on the v2 fixture page
- **WHEN** the locate call probes the cache, finds a fingerprint mismatch, invalidates, then resolves freshly through the ladder
- **THEN** the trace for the v2 run SHALL contain a `LocateEvent` row with `cache_action="invalidate"` whose `seq` is strictly less than that of a subsequent `LocateEvent` row with `cache_action="write"`

#### Scenario: No emission without trace_writer + run_id

- **GIVEN** `loop()` is called with `locator_cache` provided but no `trace_writer` or `run_id`
- **WHEN** the loop dispatches `read` calls that interact with the cache
- **THEN** no `LocateEvent` rows SHALL be emitted (there is nowhere to write them) and the loop SHALL still function correctly
