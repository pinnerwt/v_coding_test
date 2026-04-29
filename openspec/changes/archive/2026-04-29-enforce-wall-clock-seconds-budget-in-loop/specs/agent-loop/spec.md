## ADDED Requirements

### Requirement: Wall-clock seconds budget enforcement

`agent.loop.loop()` SHALL accept an optional `budget_seconds: float | None = None` keyword-only parameter. When `budget_seconds` is not `None`, the loop SHALL capture a monotonic clock reading **once** before entering the step loop and, at the **top of each iteration before any observation, planner, or LLM work**, return early with `RunResult(status="timeout", reason="seconds_budget", result=None, evidence=None, verifier=None, ...)` if `(time.monotonic() - t_loop) >= budget_seconds`. When `budget_seconds is None` (the default), the loop SHALL behave identically to before this change — no time check is performed and no new termination path is reachable.

The early-return `RunResult` SHALL preserve the cumulative metrics observed up to (but not including) the aborted iteration: `prompt_tokens`, `completion_tokens`, `usd`, `latency_ms_per_step`, `latency_ms_total`, `step_breakdown`, and `steps` (which equals the number of completed iterations, NOT the in-flight one).

`scripts.eval._run_case` SHALL pass `budget_seconds=case["budget"].get("seconds")` to `loop()` so production WebVoyager (and any future suite that defines a `seconds` budget) honors the per-case wall-clock cutoff.

#### Scenario: budget_seconds=None preserves existing behavior

- **GIVEN** a stub `LLMClient` that returns a terminal `done` tool call after 2 steps
- **WHEN** `loop(task, browser, llm_client, max_steps=20)` is called without `budget_seconds`
- **THEN** the loop SHALL complete normally with `status="succeeded"` and `steps=2`
- **AND** no `seconds_budget`-flavored termination path SHALL be reachable

#### Scenario: budget_seconds cuts off a slow loop early

- **GIVEN** a stub `LLMClient` whose `chat()` sleeps 1.0 s per call and otherwise returns a non-terminal tool call
- **WHEN** `loop(task, browser, llm_client, max_steps=100, budget_seconds=2.5)` is called
- **THEN** the loop SHALL return `RunResult(status="timeout", reason="seconds_budget", ...)`
- **AND** `steps` SHALL be between 2 and 4 inclusive (the loop terminates within ~3 seconds of wall-clock, not at the 100-step ceiling)

#### Scenario: _run_case threads the case seconds budget into loop()

- **GIVEN** a WebVoyager-style case with `case["budget"]["seconds"] == 120`
- **WHEN** `_run_case(case, ...)` invokes `loop()`
- **THEN** `loop()` SHALL be called with `budget_seconds=120`

#### Scenario: timeout RunResult preserves cumulative metrics

- **GIVEN** a stub `LLMClient` that on each call returns usage `(prompt=10, completion=5, usd=0.001)` and a non-terminal tool call, and `chat()` sleeps 1.0 s per call
- **WHEN** `loop(task, browser, llm_client, max_steps=100, budget_seconds=2.5)` returns
- **THEN** the returned `RunResult.prompt_tokens` SHALL equal `10 * steps` (plus any planner contribution)
- **AND** `RunResult.latency_ms_per_step` SHALL have exactly `steps` entries
- **AND** `RunResult.latency_ms_total` SHALL equal `sum(latency_ms_per_step)`

## MODIFIED Requirements

### Requirement: loop function

The system SHALL provide `agent.loop.loop(task, browser, llm_client, *, max_steps=20, events=None, run_id=None, trace_writer=None, locator_cache=None, expect=None, budget_seconds=None)` — a synchronous function that drives the observe → decide → act cycle and returns a `RunResult` with all metric fields populated.

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
- When `trace_writer` and `run_id` are provided (regardless of `locator_cache`), the loop SHALL emit trace events for locator ladder outcomes via `_locate_via_ladder`: a `LocateEvent(tier="L1_ax", outcome="miss")` when L1 raises `LocatorMiss(reason="zero_matches")`, a `SupervisorEvent` immediately after the supervisor decision, and a `LocateEvent(tier="L2_dom", outcome="hit"/"miss")` on the L2 attempt result. This applies whenever the ladder is actually reached; when a `locator_cache` is provided and a fresh fingerprint match short-circuits the ladder, no L1/L2 ladder events are emitted for that step.
- The new `expect: dict | None = None` kwarg SHALL be accepted and forwarded as `expect=expect` into `_build_system_prompt(task, expect=expect)` when building the initial system message. When `None` (the default), `_build_system_prompt` receives no `expect` argument and behaves identically to before this change.
- The new `budget_seconds: float | None = None` kwarg SHALL be accepted; when not `None`, the loop SHALL terminate with `RunResult(status="timeout", reason="seconds_budget", ...)` as soon as monotonic wall-clock elapsed since loop entry meets or exceeds `budget_seconds`, checked at the top of each iteration before any other work. When `None`, no wall-clock check is performed.

#### Scenario: budget_seconds appears in the loop signature

- **WHEN** `inspect.signature(agent.loop.loop).parameters` is read
- **THEN** the parameter list SHALL include `budget_seconds` as a keyword-only parameter with default `None`
