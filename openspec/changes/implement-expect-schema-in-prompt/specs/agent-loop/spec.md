## ADDED Requirements

### Requirement: System prompt includes expect schema when present

When `_build_system_prompt(task, expect=...)` is called with an `expect` dict that contains a non-empty `schema` sub-dict, the returned string SHALL include all of the following:

- The literal substring `MUST`.
- The JSON-serialized schema (e.g. `{"answer": "str"}`).
- The sorted list of required keys as a comma-separated string (e.g. `answer`).

The injected line SHALL follow the format: `Your done.result MUST be a JSON object matching this schema: <json.dumps(schema)>. Required fields: <sorted keys>.`

When `expect` is `None`, or when `expect.get("schema")` is absent or an empty dict, the returned string SHALL be byte-identical to the output of `_build_system_prompt(task)` with no `expect` argument — the new parameter MUST NOT alter the default-path output.

#### Scenario: schema present injects MUST line

- **WHEN** `_build_system_prompt("find the price", expect={"schema": {"answer": "str"}, "validators": ["answer.nonempty"]})` is called
- **THEN** the returned string SHALL contain the substring `"MUST"`
- **AND** the returned string SHALL contain the substring `"answer"`
- **AND** the returned string SHALL contain the JSON-serialized schema `'{"answer": "str"}'`

#### Scenario: schema absent leaves prompt byte-identical

- **WHEN** `_build_system_prompt("find the price")` is called with no `expect` argument
- **AND** `_build_system_prompt("find the price", expect=None)` is called
- **THEN** both calls SHALL return strings that are byte-identical to each other
- **AND** neither string SHALL contain the substring `"MUST"`

#### Scenario: required keys appear sorted

- **WHEN** `_build_system_prompt("task", expect={"schema": {"title": "str", "answer": "str"}, "validators": []})` is called
- **THEN** the returned string SHALL contain the substring `"answer, title"` (alphabetical order)
- **AND** the substring `"title, answer"` SHALL NOT appear

#### Scenario: empty schema dict leaves prompt byte-identical

- **WHEN** `_build_system_prompt("find the price", expect={"schema": {}, "validators": []})` is called
- **THEN** the returned string SHALL NOT contain the substring `"MUST"`
- **AND** the returned string SHALL be byte-identical to `_build_system_prompt("find the price")`

## MODIFIED Requirements

### Requirement: loop function

The system SHALL provide `agent.loop.loop(task, browser, llm_client, *, max_steps=20, events=None, run_id=None, trace_writer=None, locator_cache=None, expect=None)` — a synchronous function that drives the observe → decide → act cycle and returns a `RunResult` with all metric fields populated.

- `steps` SHALL equal the number of completed observe→decide→act iterations.
- `prompt_tokens`, `completion_tokens`, `usd` SHALL be cumulated from each `llm_client.chat()` call, **including the planner LLM call(s)**.
- `latency_ms_per_step` SHALL have one entry per step (wall time for the full observe→decide→dispatch cycle).
- `latency_ms_total` SHALL equal `sum(latency_ms_per_step)`.
- `step_breakdown[i]` SHALL have `step=i+1`, `latency_ms`, `prompt_tokens`, `completion_tokens`, `usd`, `tool_calls` (list of tool name strings called in that step).
- The loop SHALL call `agent.plan.plan()` once after the first observation and inject "Plan progress" into every subsequent decision user message.
- On supervisor `policy="halt"`, the loop SHALL trigger at most one `agent.plan.replan()` before returning `RunResult(status="failed")`.
- The `locator_cache: LocatorCache | None = None` kwarg SHALL be accepted and, when not `None`, threaded as the cache argument into `_locate_with_supervisor` during `read` tool dispatch with a non-empty `intent`. When `None`, the loop SHALL not pass any cache to `_locate_with_supervisor` (current default behavior is preserved for all existing callers).
- When `locator_cache` is not `None` AND `trace_writer` and `run_id` are also provided, the loop SHALL emit a `LocateEvent` for each cache action taken inside `_locate_with_supervisor`:
  - `cache_action="read"` + `outcome="hit"` + `tier="cache"` when a cached entry's live fingerprint matches.
  - `cache_action="invalidate"` + `outcome="miss"` + `tier="cache"` whenever `cache.invalidate(...)` is called.
  - `cache_action="write"` + `outcome="hit"` + `tier=<resolved ladder tier>` whenever `cache.put(...)` is called after a fresh ladder resolve.
  - The loop SHALL NOT emit a `LocateEvent` when `locator_cache is None` or when the ladder resolves without any cache interaction.
- When `trace_writer` and `run_id` are provided (regardless of `locator_cache`), the loop SHALL emit trace events for locator ladder outcomes via `_locate_via_ladder`: a `LocateEvent(tier="L1_ax", outcome="miss")` when L1 raises `LocatorMiss(reason="zero_matches")`, a `SupervisorEvent` immediately after the supervisor decision, and a `LocateEvent(tier="L2_dom", outcome="hit"/"miss")` on the L2 attempt result. This applies whenever the ladder is actually reached; when a `locator_cache` is provided and a fresh fingerprint match short-circuits the ladder, no L1/L2 ladder events are emitted for that step.
- The new `expect: dict | None = None` kwarg SHALL be accepted and forwarded as `expect=expect` into `_build_system_prompt(task, expect=expect)` when building the initial system message. When `None` (the default), `_build_system_prompt` receives no `expect` argument and behaves identically to before this change.

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
- **AND** a `LocateEvent(tier="L2_dom", outcome="hit")`

#### Scenario: Integration — real loop on correction-l1-miss-l2-hit fixture produces non-zero escalations

- **GIVEN** the `correction_l1_miss.html` fixture page (contains `<div class="btn">Submit</div>` with no ARIA role)
- **AND** a real `loop()` call with a scripted LLM client (deterministic `ChatResponse` objects — `step 1: goto(fixture_url)`, `step 2: read(intent="Submit button")`, `step 3: done(...)`)
- **AND** a real `TraceWriter` (in-memory) and `run_id`
- **WHEN** `loop()` completes and `_aggregate_diagnostics(writer, run_id)` is called
- **THEN** `escalations` SHALL contain at least one entry
- **AND** that entry SHALL have `from_tier="L1_ax"` (L1 misses because the element has no accessible role) and `to_tier` set to `"L2_dom"` or `None` (L2 may or may not match, depending on fixture)
- **AND** this assertion SHALL fail if `_emit_supervisor_event` is removed from `_locate_via_ladder` (regression guard)

#### Scenario: expect=None leaves system prompt byte-identical to pre-change output

- **WHEN** `loop(task, browser, llm_client)` is called without the `expect` argument (default `None`)
- **THEN** the system message constructed by the loop SHALL be byte-identical to the system message produced before this change was introduced
- **AND** the system message SHALL NOT contain the substring `"MUST"`

#### Scenario: expect with schema causes system message to include MUST line

- **GIVEN** `loop()` is called with `expect={"schema": {"answer": "str"}, "validators": ["answer.nonempty"]}` and a stub `LLMClient` that records the messages list and immediately returns a terminal `done` tool call
- **WHEN** the loop starts and sends the first `chat()` call
- **THEN** the system message (first element of the messages list, `role="system"`) SHALL contain the substring `"MUST"`
- **AND** SHALL contain the substring `"answer"`
