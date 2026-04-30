# agent-loop Specification

## Purpose
TBD - created by archiving change implement-loop-happy-path. Update Purpose after archive.
## Requirements
### Requirement: RunResult dataclass

The system SHALL provide `agent.loop.RunResult` — a frozen dataclass representing the outcome of a completed loop run. It SHALL have the following fields:

- `status: str` — one of `"succeeded"`, `"unverified"`, `"failed"`, `"timeout"`.
- `result: object | None` — structured result data if the task completed successfully; `None` otherwise.
- `evidence: dict | None` — evidence dict provided to `done()`; `None` when the loop did not complete via `done`.
- `verifier: dict | None` — for `done` exits: `{"ok": bool, "reasons": list[str]}` recording the evidence check outcome. `None` for `fail` and `timeout` exits.
- `steps: int = 0` — number of completed observe→decide→act iterations.
- `prompt_tokens: int = 0` — cumulative prompt tokens across all LLM calls.
- `completion_tokens: int = 0` — cumulative completion tokens across all LLM calls.
- `usd: float = 0.0` — cumulative USD cost across all LLM calls.
- `latency_ms_total: int = 0` — total wall time in ms across all steps.
- `latency_ms_per_step: list[int]` — per-step wall time in ms (length equals `steps`).
- `step_breakdown: list[dict]` — per-step breakdown dicts (length equals `steps`).

`RunResult` SHALL be frozen so callers cannot mutate it after construction.

#### Scenario: RunResult is constructible and frozen

- **WHEN** code constructs `RunResult(status="succeeded", result={"heading": "Hello"}, evidence={"url": "http://...", "text_snippet": "Hello"})`
- **THEN** the construction SHALL succeed
- **AND** `steps` SHALL equal `0` (default)
- **AND** attempting to assign to any field SHALL raise `dataclasses.FrozenInstanceError`

#### Scenario: RunResult status values are distinguishable

- **WHEN** the loop exits via `done()` with valid evidence (url + text_snippet both non-empty strings)
- **THEN** `RunResult.status` SHALL equal `"succeeded"`
- **WHEN** the loop exits via `done()` with missing or invalid evidence
- **THEN** `RunResult.status` SHALL equal `"unverified"`
- **WHEN** the loop exits via `fail(reason)`
- **THEN** `RunResult.status` SHALL equal `"failed"`
- **WHEN** the step count reaches `max_steps` without a terminal tool call
- **THEN** `RunResult.status` SHALL equal `"timeout"`

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

### Requirement: locator_cache kwarg accepted by loop with None default

`agent.loop.loop()` SHALL accept `locator_cache: LocatorCache | None = None` as a keyword-only argument. The parameter SHALL appear in the function signature after `trace_writer`. Its default value SHALL be `None`. All existing call sites that do not pass `locator_cache` SHALL continue to work without modification.

#### Scenario: Existing call sites do not require update

- **GIVEN** any existing call to `loop(task, browser, llm_client)` or `loop(task, browser, llm_client, max_steps=N)` or `loop(task, browser, llm_client, trace_writer=w, run_id=r)`
- **WHEN** the new `locator_cache` parameter is added with `None` default
- **THEN** none of those call sites SHALL require a change to continue functioning correctly

### Requirement: LocateEvent emission on cache actions

When `loop()` is called with `locator_cache` AND `trace_writer` AND `run_id`, the loop SHALL emit exactly one `LocateEvent` per cache action taken inside `_locate_with_supervisor`. Emission SHALL use a strictly-increasing `seq` allocated via `trace_writer.next_seq(run_id)` and SHALL populate `intent`, `tier`, `outcome`, `cache_action`, `chosen`, and **`step_id`** according to the action taken.

The `step_id` SHALL be set to `f"{run_id}:step-{step_num}"` where `step_num` is the loop's current 1-indexed step counter. The `step_id` SHALL be threaded from `loop()` into `_dispatch`, from `_dispatch` into `_locate_with_supervisor`, and from `_locate_with_supervisor` into `_emit_locate_event`.

- `cache_action="read"` + `outcome="hit"` + `tier="cache"` when a cached entry's live fingerprint matches.
- `cache_action="invalidate"` + `outcome="miss"` + `tier="cache"` whenever `cache.invalidate(...)` is called.
- `cache_action="write"` + `outcome="hit"` + `tier=<resolved ladder tier>` whenever `cache.put(...)` is called after a fresh ladder resolve.
- The loop SHALL NOT emit a `LocateEvent` when `locator_cache is None` or when the ladder resolves without any cache interaction.

#### Scenario: Write event emitted on first resolve into an empty cache

- **GIVEN** an empty `LocatorCache` and a `TraceWriter` open on `run_id`
- **AND** the LLM emits `read(intent="Submit button")` for a v1 fixture page on step 2
- **WHEN** the locate call resolves through the L1/L2 ladder and writes to the cache
- **THEN** exactly one `LocateEvent` row SHALL be appended with `cache_action="write"`, `outcome="hit"`, `intent="Submit button"`, `tier` equal to the ladder tier that resolved the element, **and `step_id` equal to `f"{run_id}:step-2"`**

#### Scenario: Invalidate event emitted before write on drift

- **GIVEN** a shared `LocatorCache` warmed from a v1 run
- **AND** a fresh `TraceWriter` and `run_id` for a second run on the v2 fixture page
- **WHEN** the locate call probes the cache, finds a fingerprint mismatch, invalidates, then resolves freshly through the ladder
- **THEN** the trace for the v2 run SHALL contain a `LocateEvent` row with `cache_action="invalidate"` whose `seq` is strictly less than that of a subsequent `LocateEvent` row with `cache_action="write"`
- **AND** both rows SHALL have the same `step_id` (the step that triggered the locate call)

#### Scenario: No emission without trace_writer + run_id

- **GIVEN** `loop()` is called with `locator_cache` provided but no `trace_writer` or `run_id`
- **WHEN** the loop dispatches `read` calls that interact with the cache
- **THEN** no `LocateEvent` rows SHALL be emitted (there is nowhere to write them) and the loop SHALL still function correctly

#### Scenario: LocateEvent step_id matches the step that triggered the locate call

- **GIVEN** `loop()` is called with `run_id="test-run"`, `locator_cache=<cache>`, and a `TraceWriter`
- **AND** the LLM emits `read(intent="Submit button")` on step 3
- **WHEN** the `LocateEvent` is emitted for the cache action
- **THEN** the `LocateEvent.step_id` SHALL equal `"test-run:step-3"`

### Requirement: LLM tool surface exposed by the loop

The loop SHALL expose the following tools to the LLM via `tools` in every `llm_client.chat()` call:

- `goto(url: str)` — navigate the browser to the given URL.
- `read(intent?: str)` — read visible text from the page. If `intent` is provided, the loop SHALL attempt to resolve it via `locate_l1(page, ...)` first. If `locate_l1` raises `LocatorMiss(reason="zero_matches")`, the loop SHALL invoke the `Supervisor` to get an escalation decision. If the supervisor prescribes a next tier (e.g. `"L2_dom"`), the loop SHALL retry resolution at that tier (e.g. via `locate_l2`). If resolution ultimately succeeds, the loop SHALL read the element's text via `Browser.read(selector)` and return it as the tool result. If resolution fails at all tiers, or if the intent text cannot be parsed (`IntentParseError`), the loop SHALL return an error string as the tool result and continue (SHALL NOT terminate the run). If `intent` is absent or empty, the loop SHALL return the full page body text (up to 2000 characters of `document.body.innerText`).
- `click(intent: str)` — click a page element described by `intent`. The loop SHALL resolve the element via `_locate_with_supervisor` (same ladder and cache path used by `read`). On successful resolution the loop SHALL call `Locator.click(timeout=…)` on the resolved Playwright Locator. After the click the loop SHALL emit an `ActEvent` with `outcome` in `{ok, no_effect, nav, timeout, error}`:
  - `outcome="ok"` — click completed and the page URL did not change.
  - `outcome="nav"` — click completed and the page URL changed (same-tab navigation detected).
  - `outcome="timeout"` — the Playwright `TimeoutError` was raised during the click.
  - `outcome="error"` — any other `PlaywrightError` was raised during the click.
  - `outcome="no_effect"` — reserved for future use (not emitted by this implementation).
  - `ActEvent.diff` SHALL be set to `{}` (screenshot-diff deferred to a future ticket).
  - On `LocatorMiss(reason="zero_matches")` from L1, the loop SHALL surface the miss to the supervisor for L1→L2 escalation via the existing `_locate_with_supervisor` path. If escalation succeeds, the click is retried at the resolved tier. If all tiers are exhausted (supervisor returns `policy="halt"`), the loop SHALL return an error string as the tool result and continue (SHALL NOT terminate the run).
- `type(intent: str, text: str)` — fill a textbox described by `intent` with `text`. The loop SHALL resolve the element via `_locate_with_supervisor` (same ladder and cache path used by `read` and `click`). For textbox-role intents, `locate_l2` falls back to `get_by_placeholder`, enabling L2 escalation to succeed where L1 misses on placeholder-only inputs. On successful resolution the loop SHALL call `Locator.fill(text, timeout=5000)` on the resolved Playwright Locator. After the fill the loop SHALL emit an `ActEvent` with `outcome` in `{ok, timeout, error}`:
  - `outcome="ok"` — fill completed without error.
  - `outcome="timeout"` — the Playwright `TimeoutError` was raised during the fill.
  - `outcome="error"` — any other `PlaywrightError` was raised during the fill (e.g. element is not editable).
  - `ActEvent.diff` SHALL be set to `{}` (screenshot-diff deferred to a future ticket).
  - On `LocatorMiss` from `_locate_with_supervisor` (all tiers exhausted), the loop SHALL return an error string as the tool result and continue (SHALL NOT terminate the run).
- `done(result: object, evidence: {url: str, text_snippet: str})` — terminal tool: mark the task complete. The loop SHALL validate the evidence and exit with either `RunResult(status="succeeded", ...)` or `RunResult(status="unverified", ...)` depending on the validation result.
- `fail(reason: str)` — terminal tool: mark the task failed. Under normal conditions the loop SHALL exit with `RunResult(status="failed", result=None, evidence=None, verifier=None)`. The loop SHALL apply the pre-flight validation gate (see Requirement: fail pre-flight validation gate) before accepting a `fail` call as terminal.

The loop SHALL NOT expose `select`, `wait_for`, `back`, or `screenshot` in this ticket; those are added when tests demand them.

The `TOOLS` list SHALL include a `click` entry with function name `"click"` and a required `intent` parameter of type `string`.

The `TOOLS` list SHALL include a `type` entry with function name `"type"` and required `intent` and `text` parameters, both of type `string`.

#### Scenario: LLM calls goto — browser navigates

- **GIVEN** the LLM emits a `goto` tool call with a valid URL
- **WHEN** the loop processes the tool call
- **THEN** the browser SHALL navigate to that URL (via `Browser.goto(url)`)
- **AND** the loop SHALL continue to the next iteration

#### Scenario: LLM calls read without intent — returns body text

- **GIVEN** the LLM emits a `read` tool call with no `intent` argument
- **WHEN** the loop processes the tool call
- **THEN** the loop SHALL evaluate `document.body.innerText` on the current page
- **AND** return up to 2000 characters of that text as the tool result
- **AND** continue to the next iteration

#### Scenario: LLM calls read with intent — uses locate to find element

- **GIVEN** the LLM emits a `read` tool call with `intent="the article heading"`
- **WHEN** the loop processes the tool call
- **THEN** the loop SHALL call `locate_l1(page, ...)` (or an equivalent locate call) to resolve the element
- **AND** read the element's text via `Browser.read(selector)` where `selector` is the result's selector
- **AND** return the text as the tool result
- **AND** continue to the next iteration

#### Scenario: TOOLS list includes click entry with intent parameter

- **WHEN** `agent.loop.TOOLS` is inspected
- **THEN** it SHALL contain an entry with `function.name == "click"`
- **AND** the entry's `parameters.properties` SHALL include `"intent"` with `type == "string"`
- **AND** `"intent"` SHALL appear in the `parameters.required` list

#### Scenario: LLM calls click on resolved element — ActEvent outcome=ok emitted

- **GIVEN** a fixture page with a single `<button>Submit</button>` element
- **AND** a stub LLM that emits `click(intent="Submit button")` on step 1 and `done(...)` on step 2
- **WHEN** the loop dispatches the click tool call and the button is located successfully at L1
- **THEN** `Locator.click(timeout=…)` SHALL be called on the resolved locator
- **AND** an `ActEvent` SHALL be emitted with `outcome="ok"`, `tool="click"`, and `args={"intent": "Submit button"}`
- **AND** the loop SHALL reach `done` and return `RunResult(status="succeeded")`

#### Scenario: LLM calls click and navigation occurs — ActEvent outcome=nav

- **GIVEN** a fixture page with a link-styled button that navigates to a second page when clicked
- **AND** a stub LLM that emits `click(intent="Go button")` on step 1 and `done(...)` on step 2
- **WHEN** the loop dispatches the click and the page URL changes after the click
- **THEN** an `ActEvent` SHALL be emitted with `outcome="nav"`
- **AND** the loop SHALL continue and reach `done`

#### Scenario: LLM calls click, L1 LocatorMiss triggers supervisor escalation to L2

- **GIVEN** a fixture page where the target button has no ARIA role (L1 returns `LocatorMiss(reason="zero_matches")`) but is detectable at L2
- **AND** a stub LLM that emits `click(intent="Submit button")`
- **WHEN** the loop dispatches the click and L1 raises `LocatorMiss(reason="zero_matches")`
- **THEN** the loop SHALL invoke `supervisor.handle(miss, current_tier="L1_ax")`
- **AND** the supervisor SHALL return `next_tier="L2_dom"`
- **AND** a `SupervisorEvent` with `policy="next_tier"` SHALL be emitted in the trace
- **AND** the loop SHALL proceed with `Locator.click` against the L2-resolved selector

#### Scenario: LLM calls click and Locator.click raises TimeoutError — ActEvent outcome=timeout

- **GIVEN** a click whose target is unclickable within the 5s timeout
- **WHEN** the loop dispatches click and `Locator.click(timeout=5000)` raises `playwright.sync_api.TimeoutError`
- **THEN** an `ActEvent` SHALL be emitted with `outcome="timeout"`
- **AND** the tool result SHALL be an error string starting with `"Error: click timeout"`
- **AND** the loop SHALL continue (SHALL NOT terminate the run)

#### Scenario: LLM calls click and Locator.click raises a generic PlaywrightError — ActEvent outcome=error

- **GIVEN** a click whose target raises a generic Playwright error (e.g. `"element not interactable"`)
- **WHEN** the loop dispatches click and `Locator.click(timeout=5000)` raises `playwright.sync_api.Error`
- **THEN** an `ActEvent` SHALL be emitted with `outcome="error"`
- **AND** the tool result SHALL be an error string starting with `"Error: click error"`
- **AND** the loop SHALL continue (SHALL NOT terminate the run)

#### Scenario: TOOLS list includes type entry with intent and text parameters

- **WHEN** `agent.loop.TOOLS` is inspected
- **THEN** it SHALL contain an entry with `function.name == "type"`
- **AND** the entry's `parameters.properties` SHALL include `"intent"` with `type == "string"`
- **AND** the entry's `parameters.properties` SHALL include `"text"` with `type == "string"`
- **AND** both `"intent"` and `"text"` SHALL appear in the `parameters.required` list

#### Scenario: LLM calls type on a textbox — ActEvent outcome=ok emitted, run succeeds

- **GIVEN** a fixture page with `<input type="text" placeholder="Email">` and a stub LLM that emits `type(intent="Email textbox", text="hello@example.com")` on step 1 and `done(...)` on step 2
- **WHEN** the loop dispatches the type tool call and the textbox is located successfully
- **THEN** `Locator.fill("hello@example.com", timeout=5000)` SHALL be called on the resolved locator
- **AND** an `ActEvent` SHALL be emitted with `outcome="ok"`, `tool="type"`, and `args={"intent": "Email textbox", "text": "hello@example.com"}`
- **AND** the loop SHALL reach `done` and return `RunResult(status="succeeded")`

#### Scenario: LLM calls type on non-existent intent — tool error returned, loop continues

- **GIVEN** a fixture page with no matching textbox element (all tiers miss for the given intent)
- **AND** a stub LLM that emits `type(intent="Nonexistent textbox", text="foo")`
- **WHEN** the loop dispatches the type tool call and `_locate_with_supervisor` exhausts all tiers
- **THEN** the tool result SHALL be a string starting with `"Error:"`
- **AND** the loop SHALL NOT terminate; it SHALL append the error string as a tool result and continue to the next iteration

#### Scenario: LLM calls type and Locator.fill raises TimeoutError — ActEvent outcome=timeout

- **GIVEN** a fill whose target is unresponsive within the 5s timeout
- **WHEN** the loop dispatches type and `Locator.fill(text, timeout=5000)` raises `playwright.sync_api.TimeoutError`
- **THEN** an `ActEvent` SHALL be emitted with `outcome="timeout"`
- **AND** the tool result SHALL be a string starting with `"Error: type timeout"`
- **AND** the loop SHALL continue (SHALL NOT terminate the run)

#### Scenario: LLM calls type and Locator.fill raises a generic PlaywrightError — ActEvent outcome=error

- **GIVEN** a fill whose target element is not editable (e.g. raises `"element is not an HTMLInputElement"`)
- **WHEN** the loop dispatches type and `Locator.fill(text, timeout=5000)` raises `playwright.sync_api.Error`
- **THEN** an `ActEvent` SHALL be emitted with `outcome="error"`
- **AND** the tool result SHALL be a string starting with `"Error: type error"`
- **AND** the loop SHALL continue (SHALL NOT terminate the run)

#### Scenario: LLM calls done with valid evidence — loop exits succeeded

- **GIVEN** the LLM emits a `done` tool call with a non-empty `result` and `evidence` dict containing `url` (non-empty string) and `text_snippet` (non-empty string)
- **WHEN** the loop processes the tool call
- **THEN** the loop SHALL return `RunResult(status="succeeded", result=<result>, evidence=<evidence>, verifier={"ok": True, "reasons": []})`
- **AND** SHALL NOT make any further LLM calls

#### Scenario: LLM calls fail — loop exits failed

- **GIVEN** the LLM emits a `fail` tool call with a `reason` string
- **WHEN** the loop processes the tool call
- **THEN** the loop SHALL return `RunResult(status="failed", result=None, evidence=None, verifier=None)`
- **AND** SHALL NOT make any further LLM calls

#### Scenario: LLM calls fail with no prior interaction on step 1 — call rejected, loop continues

- **GIVEN** a stub LLM that emits `fail(reason="I cannot find anything")` on step 1
- **AND** no `click` or `type` with a successful outcome has been dispatched before this step
- **WHEN** the loop encounters the `fail` tool call
- **THEN** the loop SHALL NOT return `RunResult(status="failed")`
- **AND** a `SupervisorEvent(classified_as="premature_fail")` SHALL be emitted
- **AND** the tool result appended to the message thread SHALL contain the remaining step budget and the substring `"click"` or `"type"`
- **AND** the loop SHALL continue to the next iteration

#### Scenario: LLM calls fail after a successful click — fail is honored normally

- **GIVEN** a stub LLM that emits `click(intent="Submit button")` on step 1 (outcome ok) and then `fail(reason="page did not load")` on step 2
- **WHEN** the loop encounters the `fail` tool call on step 2
- **THEN** the loop SHALL return `RunResult(status="failed", result=None, evidence=None, verifier=None)` immediately
- **AND** no `SupervisorEvent(classified_as="premature_fail")` SHALL be emitted

#### Scenario: LLM calls fail with an irrecoverable reason on step 1 — fail is honored immediately

- **GIVEN** a stub LLM that emits `fail(reason="login wall detected")` on step 1
- **AND** no prior `click` or `type` has occurred
- **WHEN** the loop encounters the `fail` tool call
- **THEN** the loop SHALL return `RunResult(status="failed", result=None, evidence=None, verifier=None)` immediately
- **AND** no `SupervisorEvent(classified_as="premature_fail")` SHALL be emitted

### Requirement: fail pre-flight validation gate

Before the loop accepts a `fail` tool call as terminal, it SHALL apply a pre-flight check. The check fires when BOTH of the following conditions hold:

- `step_num <= 1` — the `fail` call arrives on the first step of the run.
- No prior actionable outcome has been recorded for `click` or `type` in this run — i.e., no `click` dispatch returned `outcome` in `{"ok", "nav"}` and no `type` dispatch returned `outcome="ok"`.

When both conditions hold AND the `reason` string does NOT contain any irrecoverable keyword (case-insensitive substring match against `_IRRECOVERABLE_REASONS = frozenset({"login wall", "captcha", "blocked"})`), the loop SHALL:

1. Emit a `SupervisorEvent(classified_as="premature_fail", policy="halt", attempt=1)` via `_emit_supervisor_event` (or append to `events` when `trace_writer` is `None`).
2. Append a nudge string as the tool result: `"you have {max_steps - step_num} steps left and have not attempted to interact — try \`click\`/\`type\` first."` where `{max_steps - step_num}` is the number of steps remaining at the time of rejection.
3. Continue the loop to the next iteration (SHALL NOT return `RunResult(status="failed")`).

In all other cases — `step_num > 1`, or a prior actionable outcome exists, or the `reason` contains an irrecoverable keyword — the loop SHALL accept the `fail` call and return `RunResult(status="failed", result=None, evidence=None, verifier=None)` as before.

The loop SHALL track prior actionable outcomes in a local list `_prior_act_outcomes: list[str]` that is initialized to `[]` at the start of `loop()` and appended to whenever a `click` dispatch produces `outcome in {"ok", "nav"}` or a `type` dispatch produces `outcome == "ok"`. This list SHALL NOT persist across `loop()` invocations.

#### Scenario: step-1 fail with no prior interaction emits premature_fail SupervisorEvent

- **GIVEN** `loop()` is called with `max_steps=10`
- **AND** a stub LLM that emits `fail(reason="nothing useful here")` on step 1
- **AND** no `click` or `type` was dispatched before this step
- **WHEN** the `fail` branch is reached
- **THEN** a `SupervisorEvent` with `classified_as="premature_fail"` SHALL be emitted (or appended to `events` when `trace_writer` is `None`)
- **AND** the tool result SHALL contain `"9 steps left"` (i.e., `max_steps - step_num = 10 - 1 = 9`)
- **AND** the tool result SHALL contain `"click"` and `"type"`
- **AND** the loop SHALL NOT return at this point; it SHALL continue to the next step

#### Scenario: fail on step 2 after step-1 read is honored normally

- **GIVEN** a stub LLM that emits `read()` on step 1 and `fail(reason="could not find result")` on step 2
- **AND** no `click` or `type` was dispatched
- **WHEN** the `fail` branch is reached on step 2
- **THEN** the loop SHALL return `RunResult(status="failed")` immediately
- **AND** no `SupervisorEvent(classified_as="premature_fail")` SHALL be emitted

#### Scenario: fail with reason containing "login wall" is honored on step 1

- **GIVEN** a stub LLM that emits `fail(reason="Encountered a login wall")` on step 1
- **AND** no prior `click` or `type` occurred
- **WHEN** the `fail` branch is reached
- **THEN** the loop SHALL return `RunResult(status="failed")` immediately (irrecoverable keyword match)
- **AND** no `SupervisorEvent(classified_as="premature_fail")` SHALL be emitted

#### Scenario: fail with reason containing "captcha" is honored on step 1

- **GIVEN** a stub LLM that emits `fail(reason="CAPTCHA encountered, cannot proceed")` on step 1
- **AND** no prior `click` or `type` occurred
- **WHEN** the `fail` branch is reached
- **THEN** the loop SHALL return `RunResult(status="failed")` immediately
- **AND** no `SupervisorEvent(classified_as="premature_fail")` SHALL be emitted

#### Scenario: step-1 fail after successful click is honored normally

- **GIVEN** a stub LLM that emits `click(intent="Submit button")` on step 1 (outcome ok) then `fail(reason="submit failed")` on step 1 (second tool call in same step)
- **WHEN** the `fail` branch is reached
- **THEN** `_prior_act_outcomes` is non-empty (contains `"ok"` from the click)
- **AND** the loop SHALL return `RunResult(status="failed")` immediately
- **AND** no `SupervisorEvent(classified_as="premature_fail")` SHALL be emitted

### Requirement: Happy-path 2-step task completion

The system SHALL support completing a 2-step task on a local HTML fixture: step 1 navigate to a page, step 2 read a value and call `done` with valid evidence. This is the acceptance criterion for ticket #9.

The evidence dict passed to `done` SHALL contain at minimum `url` (the current page URL) and `text_snippet` (a non-empty string of visible page text confirming the result). The loop SHALL treat any non-empty evidence dict with these two keys as valid for the happy path.

#### Scenario: 2-step task completes with succeeded status

- **GIVEN** a local HTML fixture page with a known heading
- **AND** a mock LLM that emits: step 1 → `goto(url=<fixture_url>)`, step 2 → `done(result={"heading": <text>}, evidence={"url": <fixture_url>, "text_snippet": <text>})`
- **WHEN** `loop(task, browser, mock_llm_client)` is called
- **THEN** the return value SHALL be a `RunResult` with `status="succeeded"`
- **AND** `RunResult.evidence` SHALL be a dict with non-empty `url` and `text_snippet` values
- **AND** `RunResult.result` SHALL be the dict passed to `done`

#### Scenario: Evidence is present in the RunResult

- **GIVEN** a successful `done` call with `evidence={"url": "http://127.0.0.1:<port>/loop_happy_path.html", "text_snippet": "Hello, loop"}`
- **WHEN** the loop returns
- **THEN** `RunResult.evidence["url"]` SHALL be a non-empty string
- **AND** `RunResult.evidence["text_snippet"]` SHALL be a non-empty string

### Requirement: LLM_BASE_URL and LLM_MODEL remain configurable

The loop SHALL NOT hardcode any LLM provider URL or model name. All LLM configuration SHALL come from the `LLMClient` instance passed to `loop()`. The loop SHALL pass `llm_client` through unmodified; it SHALL NOT construct its own `LLMClient` internally.

#### Scenario: Loop uses caller-supplied LLMClient

- **WHEN** `loop(task, browser, llm_client)` is called with a custom `LLMClient` configured to use a specific `base_url`
- **THEN** all LLM calls in the loop SHALL go through that `llm_client` instance
- **AND** the loop SHALL NOT read `LLM_BASE_URL` or `LLM_MODEL` environment variables directly

### Requirement: Loop self-correction via supervisor escalation

When the `read` tool dispatch encounters a `LocatorMiss(reason="zero_matches")` from the initial locate attempt, the loop SHALL invoke the `Supervisor` to classify the miss and obtain an escalation decision. If the supervisor returns `next_tier="L2_dom"`, the loop SHALL retry locate at L2. If L2 succeeds, the loop SHALL use the L2 result to read the element and return the text. If the supervisor halts (no `next_tier`), the loop SHALL return an error string as the tool result and continue. This requirement is the acceptance criterion for ticket #10.

The `Supervisor` instance SHALL be created once per `loop()` invocation so that attempt counters accumulate correctly across multiple locate failures within the same run.

#### Scenario: L1 fails with zero_matches, L2 succeeds — loop self-corrects

- **GIVEN** a fixture page where a button has `aria-label="action"` (so `get_by_role("button", name="Submit")` returns zero matches) but has visible text "Submit" (so `locate_l2` with role="button", name="Submit" succeeds)
- **AND** a mock LLM that emits: step 1 → `goto(url=<fixture_url>)`, step 2 → `read(intent="Submit button")`, step 3 → `done(result={"clicked": true}, evidence={...})`
- **WHEN** `loop(task, browser, mock_llm_client)` is called
- **THEN** the loop SHALL attempt L1 locate for "Submit button", receive `LocatorMiss(reason="zero_matches")`
- **AND** invoke the `Supervisor` which SHALL return `next_tier="L2_dom"`
- **AND** retry via L2 which SHALL succeed
- **AND** return `RunResult(status="succeeded")` after the `done` call

#### Scenario: Supervisor escalation path is exercised — test fails without wiring

- **GIVEN** `loop.py` does NOT wire the supervisor into read dispatch (supervisor is never called)
- **WHEN** the self-correction test fixture is used and `read(intent="Submit button")` is dispatched
- **THEN** the loop SHALL either raise an unhandled `LocatorMiss` or return an error tool result that prevents the LLM from calling `done`
- **AND** the test SHALL fail, confirming the test is a valid regression guard

#### Scenario: Supervisor max_attempts cap — loop halts gracefully after exhaustion

- **GIVEN** the supervisor's `max_attempts` is reached for the `(current_tier, reason)` pair
- **WHEN** the loop calls `supervisor.handle(miss, current_tier=...)`
- **THEN** the supervisor SHALL return `EscalationDecision(next_tier=None, policy="halt", ...)`
- **AND** the loop SHALL feed an error string back to the LLM as the tool result (not raise or crash)
- **AND** continue to the next loop iteration

### Requirement: done evidence guard

When the LLM calls the `done` tool, the loop SHALL validate the `evidence` argument before committing to `status="succeeded"`. The guard checks two required fields:

- `url`: must be present in the evidence dict and be a non-empty string (after stripping whitespace).
- `text_snippet`: must be present in the evidence dict and be a non-empty string (after stripping whitespace).

If either field is absent, not a string, or empty after stripping whitespace, the guard SHALL mark the run `"unverified"`. The guard SHALL construct a `verifier` dict of shape `{"ok": bool, "reasons": list[str]}` that records which checks failed. This `verifier` dict SHALL be attached to the `RunResult`.

`screenshot_ref` is part of the planned `DoneEvent.evidence` shape but is NOT validated by this guard; its validation is deferred to the screenshot-diff feature (a separate future ticket).

#### Scenario: done called with empty evidence dict — status is unverified

- **GIVEN** the LLM emits a `done` tool call with `evidence={}`
- **WHEN** the loop processes the tool call
- **THEN** `RunResult.status` SHALL equal `"unverified"`
- **AND** `RunResult.verifier["ok"]` SHALL be `False`
- **AND** `RunResult.verifier["reasons"]` SHALL be a non-empty list of strings describing the missing fields

#### Scenario: done called with evidence missing text_snippet — status is unverified

- **GIVEN** the LLM emits a `done` tool call with `evidence={"url": "http://example.com"}`
- **WHEN** the loop processes the tool call
- **THEN** `RunResult.status` SHALL equal `"unverified"`
- **AND** `RunResult.verifier["ok"]` SHALL be `False`
- **AND** `RunResult.verifier["reasons"]` SHALL mention `text_snippet`

#### Scenario: done called with evidence missing url — status is unverified

- **GIVEN** the LLM emits a `done` tool call with `evidence={"text_snippet": "some text"}`
- **WHEN** the loop processes the tool call
- **THEN** `RunResult.status` SHALL equal `"unverified"`
- **AND** `RunResult.verifier["ok"]` SHALL be `False`
- **AND** `RunResult.verifier["reasons"]` SHALL mention `url`

#### Scenario: done called with no evidence argument — status is unverified

- **GIVEN** the LLM emits a `done` tool call with no `evidence` key in args
- **WHEN** the loop processes the tool call
- **THEN** `RunResult.status` SHALL equal `"unverified"`
- **AND** `RunResult.verifier["ok"]` SHALL be `False`

#### Scenario: done called with valid evidence — status is succeeded, verifier ok

- **GIVEN** the LLM emits a `done` tool call with `evidence={"url": "http://example.com", "text_snippet": "Hello"}`
- **WHEN** the loop processes the tool call
- **THEN** `RunResult.status` SHALL equal `"succeeded"`
- **AND** `RunResult.verifier["ok"]` SHALL be `True`
- **AND** `RunResult.verifier["reasons"]` SHALL be an empty list

#### Scenario: existing happy-path test stays green

- **GIVEN** a mock LLM that emits `done` with `evidence={"url": <fixture_url>, "text_snippet": "Hello, loop"}`
- **WHEN** `loop(task, browser, mock_llm_client)` is called
- **THEN** `RunResult.status` SHALL equal `"succeeded"` (no regression from ticket #9)
- **AND** `RunResult.evidence["url"]` and `RunResult.evidence["text_snippet"]` SHALL be non-empty strings

### Requirement: loop observation uses AX-tree digest

The loop SHALL call `observe.build_observation(browser, last_actions)` at the start of each step instead of constructing the observation inline. The returned dict (with keys `url`, `title`, `ax_tree_digest`, `ax_fingerprint`, `last_actions`) SHALL be serialized to JSON and appended to the LLM message thread as a user message prefixed by `STATE_MESSAGE_PREFIX`. The loop SHALL accumulate `last_actions` across all tool dispatches within a single step: at the start of each iteration the loop SHALL call `build_observation(browser, last_actions)` with the list accumulated during the **previous** iteration's dispatches; immediately after that call `last_actions` SHALL be reset to `[]` before any new dispatches in the current iteration; after each non-terminal tool dispatch it SHALL append `{tool: <name>, intent: <string summary of args>, outcome: <"ok"|"error">, error?: <message>}`.

#### Scenario: First step has last_actions empty list in observation

- **WHEN** the loop calls `observe.build_observation(browser, last_actions)` for the first time (step 1)
- **THEN** `last_actions` SHALL be `[]`
- **AND** the serialized user message SHALL contain `"last_actions": []`

#### Scenario: Second step threads previous last_actions

- **GIVEN** a loop where step 1 dispatched a `goto` tool call that succeeded
- **WHEN** the loop calls `observe.build_observation(browser, last_actions)` at the start of step 2
- **THEN** `last_actions` SHALL be a list of length 1 containing a dict with at least keys `tool` (value `"goto"`) and `outcome` (value `"ok"`)
- **AND** the serialized user message SHALL contain the `last_actions` list

#### Scenario: Multi-tool step produces last_actions with all actions in order

- **GIVEN** a single LLM response that contains two tool calls: first `goto(url=<fixture_url>)` then `read()`
- **WHEN** both tool calls are dispatched in that step and the loop reaches the next observation
- **THEN** `last_actions` SHALL be a list of length 2
- **AND** `last_actions[0]["tool"]` SHALL equal `"goto"`
- **AND** `last_actions[1]["tool"]` SHALL equal `"read"`
- **AND** both entries SHALL have an `"outcome"` key

#### Scenario: Error outcome is preserved per action in last_actions

- **GIVEN** a single LLM response with two tool calls where the first succeeds and the second returns an error
- **WHEN** both are dispatched in that step and the loop reaches the next observation
- **THEN** `last_actions[0]["outcome"]` SHALL equal `"ok"`
- **AND** `last_actions[1]["outcome"]` SHALL equal `"error"`
- **AND** `last_actions[1]` SHALL contain an `"error"` key with the error message string

#### Scenario: Single-tool-call step produces length-1 last_actions (no regression)

- **GIVEN** a single LLM response that contains exactly one tool call (`goto`)
- **WHEN** the tool call is dispatched and the loop reaches the next observation
- **THEN** `last_actions` SHALL be a list of length 1
- **AND** `last_actions[0]["tool"]` SHALL equal `"goto"`

#### Scenario: Observation message contains last_actions key (not last_action)

- **GIVEN** a loop step where `observe.build_observation` returns a dict with `last_actions`
- **WHEN** the loop appends the observation to the LLM message thread
- **THEN** the serialized JSON SHALL contain the key `"last_actions"`
- **AND** SHALL NOT contain the legacy key `"last_action"` (singular)

#### Scenario: Observation message contains ax_tree_digest key

- **GIVEN** a loop step where `observe.build_observation` returns a dict with `ax_tree_digest`
- **WHEN** the loop appends the observation to the LLM message thread
- **THEN** the serialized JSON SHALL contain the key `"ax_tree_digest"`
- **AND** SHALL NOT contain the legacy key `"text"` (the old innerText observation)

### Requirement: loop calls plan() after first observation and emits PlanEvent before first DecisionEvent

After obtaining the first observation (step 1), the loop SHALL call `agent.plan.plan(task, observation, llm_client)` to produce an initial `Plan`. It SHALL then emit a `PlanEvent(reason="initial", steps=plan.steps, llm_call_id=<planner_llm_call_id>)` before issuing the first `DecisionEvent`. The `PlanEvent` SHALL appear before any `DecisionEvent` in the event sequence for any run.

#### Scenario: PlanEvent emitted before first DecisionEvent on fixture run

- **GIVEN** a loop run on a fixture page where the mock LLM returns a valid plan JSON on the first planner call
- **WHEN** the loop completes
- **THEN** the sequence of emitted events SHALL contain a `PlanEvent(reason="initial")` occurring before the first `DecisionEvent`

#### Scenario: PlanEvent contains the steps from the planner response

- **GIVEN** a mock LLM planner that returns `{"steps": ["step A", "step B"], "expected_end_state": "done"}`
- **WHEN** the loop runs and emits a `PlanEvent`
- **THEN** the `PlanEvent.steps` SHALL equal `["step A", "step B"]`

### Requirement: Plan steps injected into decision prompts from step 1 onwards

From step 1 (after the initial plan is established), each decision-step user message SHALL include a "Plan progress" block immediately before the observation JSON. The block SHALL contain all plan steps as a numbered list. No per-step completion tracking is performed; all steps appear in every message regardless of progress.

The format SHALL be:
```
Plan progress:
1. <step 1>
2. <step 2>
...

Current state: <observation json>
```

#### Scenario: Step 1 decision prompt includes Plan progress block

- **GIVEN** a loop with a mock LLM that captures the messages passed to it on each call
- **AND** the planner returned `{"steps": ["find result", "return it"], "expected_end_state": "done"}`
- **WHEN** the loop makes the decision LLM call for step 1 (the first decision after planning)
- **THEN** the user message content SHALL contain the substring `"Plan progress:"`
- **AND** SHALL contain `"1. find result"`
- **AND** SHALL contain `"2. return it"`

#### Scenario: Plan progress block appears on all subsequent decision steps

- **GIVEN** a multi-step run where the LLM calls `goto` on step 1 and `done` on step 2
- **WHEN** the messages for the step 2 decision call are inspected
- **THEN** the user message for step 2 SHALL also contain `"Plan progress:"`

### Requirement: Supervisor halt triggers one replan before terminal failure

When `_locate_with_supervisor` causes the supervisor to return `policy="halt"` (the locator pipeline is exhausted), the loop SHALL check whether a replan has already been used in this run. If no replan has been used yet, the loop SHALL:

1. Call `agent.plan.replan(task, observation, prior_plan, reason, llm_client)`.
2. Emit `PlanEvent(reason="replan", steps=new_plan.steps, llm_call_id=<replan_llm_call_id>)`.
3. Replace the active plan with the new plan and continue the loop.

If a replan has already been used (i.e., this is the second halt), the loop SHALL treat it as a terminal failure and return `RunResult(status="failed", ...)`.

#### Scenario: First supervisor halt triggers replan and loop continues

- **GIVEN** a mock browser fixture where the locator always misses on step 1 (triggering supervisor halt)
- **AND** the supervisor has not yet used its replan budget
- **AND** the mock LLM returns a valid replan JSON
- **WHEN** the loop processes the halt
- **THEN** a `PlanEvent(reason="replan")` SHALL be emitted
- **AND** the loop SHALL continue to the next step

#### Scenario: Second supervisor halt after replan is terminal failure

- **GIVEN** a run where the first halt triggered a replan
- **WHEN** the supervisor halts again on a subsequent step
- **THEN** the loop SHALL return `RunResult(status="failed", ...)`
- **AND** SHALL NOT emit a second `PlanEvent(reason="replan")`

### Requirement: click tool dispatch in loop

The loop SHALL handle `tool_call.name == "click"` in `_dispatch`. The dispatch contract is:

1. Call `_locate_with_supervisor(page, intent, supervisor, cache=locator_cache, trace_writer=trace_writer, run_id=run_id, step_id=step_id)` to resolve the element.
2. Record `url_before = page.url`.
3. Call `page.locator(result.selector).click(timeout=5000)`.
4. If click succeeds: compare `page.url` to `url_before`. If changed → `outcome="nav"`, else → `outcome="ok"`.
5. If `playwright.sync_api.TimeoutError` raised → `outcome="timeout"`.
6. If any other `playwright.sync_api.Error` raised → `outcome="error"`.
7. Emit `ActEvent(tool="click", args={"intent": intent}, outcome=<outcome>, diff={}, ms=<elapsed_ms>)`.
8. Return a string summarising the outcome to the LLM (e.g. `"Clicked 'Submit button' (ok)"` or `"Error: click timeout for intent 'Submit button'"`).
9. On `LocatorMiss` from `_locate_with_supervisor` (all tiers exhausted): return an error string and continue (do NOT terminate the run).

The `ToolName` literal in `loop.py` SHALL be updated to include `"click"`.

#### Scenario: click dispatch returns ok string when element found and clicked

- **GIVEN** a page with a `<button>Submit</button>` element that L1 locates successfully
- **WHEN** `_dispatch("click", {"intent": "Submit button"}, browser, supervisor, ...)` is called
- **THEN** it SHALL return a non-error string (not starting with `"Error:"`)
- **AND** an `ActEvent` with `outcome="ok"` SHALL be emitted

#### Scenario: click dispatch returns error string on LocatorMiss — loop continues

- **GIVEN** a page with no button element (all tiers miss)
- **WHEN** `_dispatch("click", {"intent": "Nonexistent button"}, browser, supervisor, ...)` is called
- **THEN** it SHALL return a string starting with `"Error:"`
- **AND** the loop SHALL NOT terminate; it SHALL append the error string as a tool result and continue to the next iteration

### Requirement: type tool dispatch in loop

The loop SHALL handle `tool_call.name == "type"` in `_dispatch`. The dispatch contract is:

1. Extract `intent` and `text` from `args`. If either is absent or not a non-empty string, return an error string immediately (do NOT call locate).
2. Call `_locate_or_error_msg(page, intent, supervisor, cache=locator_cache, trace_writer=trace_writer, run_id=run_id, step_id=step_id)` to resolve the element. If locate returns an error string, return it and continue.
3. Record `t_fill = time.monotonic()`.
4. Call `page.locator(result.selector).fill(text, timeout=5000)`.
5. If fill succeeds → `outcome="ok"`.
6. If `playwright.sync_api.TimeoutError` raised → `outcome="timeout"`.
7. If any other `playwright.sync_api.Error` raised → `outcome="error"`.
8. Compute `elapsed_ms = int((time.monotonic() - t_fill) * 1000)`.
9. Emit `ActEvent(tool="type", args={"intent": intent, "text": text}, outcome=outcome, diff={}, ms=elapsed_ms)`.
10. Return `f"Typed into {intent!r} (ok)"` on success or `f"Error: type {outcome} for intent {intent!r}"` on failure.

The `ToolName` literal in `loop.py` SHALL be updated to include `"type"`.

Note: `ActEvent.tool` is typed as `str` in `agent/trace.py` — no schema change to `trace.py` is required.

#### Scenario: type dispatch returns ok string when textbox found and filled

- **GIVEN** a page with `<input type="text" placeholder="Email">` that `_locate_with_supervisor` resolves at L1 or L2
- **WHEN** `_dispatch("type", {"intent": "Email textbox", "text": "hello@example.com"}, browser, supervisor, ...)` is called
- **THEN** it SHALL return a non-error string (not starting with `"Error:"`)
- **AND** an `ActEvent` with `outcome="ok"` and `tool="type"` SHALL be emitted

#### Scenario: type dispatch returns error string on LocatorMiss — loop continues

- **GIVEN** a page with no matching textbox (all tiers miss)
- **WHEN** `_dispatch("type", {"intent": "Nonexistent textbox", "text": "foo"}, browser, supervisor, ...)` is called
- **THEN** it SHALL return a string starting with `"Error:"`
- **AND** the loop SHALL NOT terminate; it SHALL append the error string as a tool result and continue to the next iteration

### Requirement: System prompt fail guidance content

The string returned by `_build_system_prompt` SHALL contain `fail`-gate guidance that:

1. Uses the phrase `"ONLY for irrecoverable conditions"` to gate when `fail` is appropriate.
2. Names the accepted irrecoverable conditions: login walls, captchas, pages that don't exist, or required information genuinely absent from the page.
3. Instructs the model to attempt `click`/`type` with a natural-language `intent` first when a target element exists on the page but the action is uncertain, noting that the locator pipeline will resolve it.

The old unconditional phrasing ("If you cannot complete the task, call `fail` with a reason.") SHALL NOT appear in the returned string.

#### Scenario: system prompt contains ONLY-for phrasing

- **WHEN** `_build_system_prompt("any task")` is called
- **THEN** the returned string SHALL contain the substring `"ONLY for irrecoverable conditions"`

#### Scenario: system prompt contains action-first guidance

- **WHEN** `_build_system_prompt("any task")` is called
- **THEN** the returned string SHALL contain the substring `"attempt \`click\`/\`type\`"`

#### Scenario: system prompt does not contain unconditional fail invitation

- **WHEN** `_build_system_prompt("any task")` is called
- **THEN** the returned string SHALL NOT contain the substring `"If you cannot complete the task, call"`

#### Scenario: system prompt names irrecoverable conditions

- **WHEN** `_build_system_prompt("any task")` is called
- **THEN** the returned string SHALL contain the substrings `"login walls"`, `"captchas"`, `"pages that don't exist"`, and `"required information genuinely absent from the page"`

### Requirement: Message history compaction

The system SHALL provide a private function `_compact_messages(messages: list[dict], budget_chars: int) -> list[dict]` in `agent/loop.py` that reduces the serialized size of the `messages` list to stay under `budget_chars` characters (measured as `sum(len(json.dumps(m)) for m in messages)`) by **dropping** the oldest non-system, non-most-recent-state messages. The kept messages SHALL be byte-identical to the input messages — the function SHALL NOT mutate any message's `content`, `role`, or any other field.

Rules:
1. `messages[0]` (the system prompt, `role == "system"`) SHALL never be modified or removed.
2. The most recent state turn SHALL be kept verbatim. The "most recent state" is defined as the last `user`-role message whose `content` contains the substring `"Current state: "`. This message and any messages after it (e.g. the most recent `tool` results corresponding to the upcoming decision) SHALL never be dropped.
3. To bring `total <= budget_chars`, the function SHALL drop messages from index `1` upward (i.e. oldest first); the drop boundary `drop_idx` SHALL NOT exceed `last_state_idx`.
4. The function SHALL drop *whole messages*; it SHALL NOT mutate any kept message's content. A kept message in the result SHALL satisfy `kept_message is input_message_at_some_index_j` for some `j` in the original list.
5. The kept tail SHALL begin at a turn boundary — after the size-based drop completes, the function SHALL advance the drop boundary forward (without exceeding `last_state_idx`, which is itself a state message and thus a valid stop) until the next kept non-system message is a user-role state message. This prevents orphaning a `tool` message whose corresponding `assistant` `tool_calls` parent has been dropped, which OpenAI-compatible LLM APIs reject.
6. When `total <= budget_chars` on entry, the function SHALL return `messages` unchanged.
7. When even `[messages[0], messages[last_state_idx:]]` exceeds `budget_chars`, the function SHALL return that minimum-keep set rather than dropping the system or last-state messages. The LLM client is responsible for handling the oversize prompt in that pathological case.
8. When `last_state_idx is None` (no user-role state message present), the function SHALL NOT drop any messages — it returns the input list unchanged. This case is unreachable under the production loop, which always appends a fresh state message before invoking the function.

The loop function (`agent.loop.loop`) SHALL call `_compact_messages(messages, _budget)` immediately before every `llm_client.chat(messages, tools=TOOLS)` call, where `_budget` is read from the environment variable `LLM_CONTEXT_CHAR_BUDGET` (parsed as `int`) or falls back to the module-level constant `_DEFAULT_CONTEXT_CHAR_BUDGET = 80_000`.

The constants `_ELIDED_STATE_CONTENT` and `_ELIDED_TOOL_CONTENT` SHALL NOT exist in `agent/loop.py` — they are dead code under the drop-based contract.

#### Scenario: compaction fires by dropping when messages exceed budget

- **GIVEN** a stub `LLMClient` that always returns a `goto` tool call
- **AND** a stub browser that returns ≥ 4 KB AX-tree JSON observations per step
- **WHEN** `loop("task", browser, llm_client, max_steps=25)` runs to timeout
- **THEN** the `messages` argument passed to the stub's last `chat()` call SHALL have `sum(len(json.dumps(m)) for m in messages) < 80_000`
- **AND** no `user`-role message in the result SHALL have `content == "Current state: <elided>"`
- **AND** no `tool`-role message in the result SHALL have `content == "<read tool result elided>"`
- **AND** `messages[0]["role"]` SHALL equal `"system"`

#### Scenario: most recent observation is never dropped

- **GIVEN** the same stub setup as above
- **WHEN** the loop runs to timeout with compaction active
- **THEN** the last `user`-role message in the original (pre-compaction) list whose `content` contains the substring `"Current state: "` SHALL be present byte-identically in the post-compaction list
- **AND** `messages[0]["content"]` SHALL equal `_build_system_prompt("task")` verbatim

#### Scenario: compaction is a no-op when under budget

- **GIVEN** a `messages` list whose `sum(len(json.dumps(m)) ...)` is less than `budget_chars`
- **WHEN** `_compact_messages(messages, budget_chars)` is called
- **THEN** the returned list SHALL be identical to the input (no mutations)

#### Scenario: kept messages are byte-identical to inputs

- **GIVEN** an oversized `messages` list
- **WHEN** `_compact_messages(messages, budget_chars)` is called and returns a list `result`
- **THEN** for every `m` in `result`, there SHALL exist an index `j` such that `m == messages[j]` field-for-field (no `content` rewriting)
- **AND** the substring `"<elided>"` SHALL NOT appear in any `result[i]["content"]` value

#### Scenario: prefix stability across consecutive compactions

- **GIVEN** a list `L1` that exceeds `budget_chars`, compacted to `R1 = _compact_messages(L1, budget_chars)`
- **AND** a list `L2 = L1 + [new_state_msg, new_tool_msg]` (new turn appended) that also exceeds `budget_chars`, compacted to `R2 = _compact_messages(L2, budget_chars)`
- **THEN** the kept overlap region of `R2` (i.e. messages in `R2` that originated from `L1`) SHALL be a contiguous tail of `R1` — formally, there SHALL exist indices `k, m` such that `R2[1:m] == R1[k:]` field-for-field
- **AND** this property SHALL hold even when more messages were dropped on the second pass than on the first

#### Scenario: no state message present is a no-op

- **GIVEN** a `messages` list whose total size exceeds `budget_chars`
- **AND** no `user`-role message in the list contains the substring `"Current state: "` (i.e. `last_state_idx` is `None`)
- **WHEN** `_compact_messages(messages, budget_chars)` is called
- **THEN** the function SHALL return `messages` unchanged (the same list object)
- **AND** the function SHALL NOT drop or mutate any message

#### Scenario: drops align to turn boundaries

- **GIVEN** a `messages` list whose interior turns each contain `[user_state, assistant_with_tool_calls, tool_result]`
- **WHEN** `_compact_messages` drops oldest messages to fit `budget_chars`
- **THEN** every kept `tool` message's `tool_call_id` SHALL match a kept `assistant` message's `tool_calls[*].id`
- **AND** the first non-system message in the result (when present) SHALL be a `user`-role state message

### Requirement: RunResult carries an optional reason field

`agent.loop.RunResult` SHALL carry a field `reason: RunResultReason | None = None`, where `RunResultReason = Literal["stuck_repeat", "no_tool_call_repeat", "seconds_budget", "no_progress"]` is a module-level alias declared alongside `RunStatus`. The field SHALL default to `None` so all existing construction sites that do not pass `reason` continue to compile and run without modification. When the loop exits via stuck-state early-termination (K identical tool calls), the field SHALL be set to `"stuck_repeat"`. When the loop exits via no-tool-call early-termination (K consecutive responses with no tool calls), the field SHALL be set to `"no_tool_call_repeat"`. When the loop exits via wall-clock budget exhaustion, the field SHALL be set to `"seconds_budget"`. When the loop exits via no-progress stuck detection (N consecutive steps with same AX fingerprint and no successful action), the field SHALL be set to `"no_progress"`. For all other terminal paths (`done`, `fail`, `timeout` from `max_steps`, supervisor halt) the field SHALL remain `None` unless explicitly set by that path. Future failure modes SHALL be added as deliberate extensions of the `RunResultReason` Literal alias rather than as free-text strings.

#### Scenario: RunResult constructed without reason defaults to None

- **WHEN** `RunResult(status="succeeded", result={}, evidence={"url": "http://x", "text_snippet": "x"})` is constructed
- **THEN** `result.reason` SHALL be `None`

#### Scenario: RunResult constructed with stuck_repeat reason preserves the value

- **WHEN** `RunResult(status="failed", result=None, evidence=None, reason="stuck_repeat")` is constructed
- **THEN** `result.reason` SHALL equal `"stuck_repeat"`

#### Scenario: RunResult constructed with no_tool_call_repeat reason preserves the value

- **WHEN** `RunResult(status="failed", result=None, evidence=None, reason="no_tool_call_repeat")` is constructed
- **THEN** `result.reason` SHALL equal `"no_tool_call_repeat"`

#### Scenario: RunResult constructed with no_progress reason preserves the value

- **WHEN** `RunResult(status="failed", result=None, evidence=None, reason="no_progress")` is constructed
- **THEN** `result.reason` SHALL equal `"no_progress"`

### Requirement: Loop terminates early when LLM emits K identical tool calls in a row

`agent.loop.loop()` SHALL maintain a rolling buffer `_stuck_buf` of the last `_STUCK_REPEAT_K` canonical tool-call strings, where each entry is `f"{tool_name}:{json.dumps(args, sort_keys=True)}"` and `_STUCK_REPEAT_K = 3` is a module-level constant. After each LLM response that contains at least one tool call, the loop SHALL dispatch each tool call, append the canonical string for that call to `_stuck_buf`, trim `_stuck_buf` to the last `_STUCK_REPEAT_K` entries, and check whether all `_STUCK_REPEAT_K` entries are byte-identical. If they are, the loop SHALL immediately call `_record_step(...)` and return:

- `RunResult(status="failed", reason="stuck_repeat", result=None, evidence=None, verifier=None, steps=step_num, ...)`

The `_stuck_buf` SHALL be initialized to `[]` at the start of `loop()` and SHALL NOT be reset between steps (it is a rolling window across the entire run). However, if the supervisor handles a tool call during dispatch (detected by snapshotting the supervisor's attempt count before dispatch and observing an increase after), the buffer SHALL be cleared, and the current call's canonical entry SHALL then be appended to the empty buffer. This ensures supervisor-mediated repetition is owned by the supervisor's halt/replan path rather than stuck-detection.

#### Scenario: Three identical goto calls in a row trigger stuck exit at step 3

- **GIVEN** a stub `LLMClient` that always returns `goto(url="about:blank")` as its tool call (no `done`/`fail`)
- **AND** `loop()` is called with `max_steps=20`
- **WHEN** the loop runs
- **THEN** `RunResult.status` SHALL equal `"failed"`
- **AND** `RunResult.reason` SHALL equal `"stuck_repeat"`
- **AND** `RunResult.steps` SHALL equal `3` (exits at step 3, not step 20)

#### Scenario: Healthy alternation of tool calls does not false-positive stuck detection

- **GIVEN** a stub `LLMClient` that emits `goto(url="http://a")` on step 1, `goto(url="http://b")` on step 2, `goto(url="http://a")` on step 3, and a no-tool-call response on every subsequent step (alternating URLs prevent all K entries from being identical)
- **AND** `loop()` is called with `max_steps=20`
- **WHEN** the loop runs
- **THEN** `RunResult.reason` SHALL NOT equal `"stuck_repeat"` (the alternation does not false-positive stuck-detection); the loop instead exits via `no_tool_call_repeat` once steps 4-6 emit no tool calls (see the no-tool-call early-termination requirement below)

#### Scenario: Stuck exit fires before max_steps is exhausted for non-supervisor tools

- **GIVEN** a stub `LLMClient` that always returns the same `goto(url="about:blank")` tool call
- **AND** `loop()` is called with `max_steps=20`
- **WHEN** the loop runs
- **THEN** `RunResult.steps` SHALL be less than `20`
- **AND** `RunResult.status` SHALL equal `"failed"`
- **AND** `RunResult.reason` SHALL equal `"stuck_repeat"`

### Requirement: Loop terminates early when LLM emits K consecutive responses with no tool calls

`agent.loop.loop()` SHALL maintain a counter `_consecutive_no_tool_call_steps` initialized to `0` at the start of `loop()`, alongside a module-level constant `_NO_TOOL_CALL_K = 3`. On each step where `step_num > 0` and the LLM response yields `len(response.tool_calls) == 0` (or `None`), the counter SHALL be incremented by 1. On each step where the LLM response yields at least one tool call, the counter SHALL be reset to `0`. When the counter reaches `_NO_TOOL_CALL_K`, the loop SHALL immediately call `_record_step(...)` and return:

- `RunResult(status="failed", reason="no_tool_call_repeat", result=None, evidence=None, verifier=None, steps=step_num, prompt_tokens=cum_prompt_tokens, completion_tokens=cum_completion_tokens, usd=cum_usd, latency_ms_total=sum(latency_ms_per_step), latency_ms_per_step=latency_ms_per_step, step_breakdown=step_breakdown)`

The plan step at step 0 (where `plan_module.plan()` is called directly and the LLM response does not pass through the tool-call dispatch path) SHALL NOT count toward the `_consecutive_no_tool_call_steps` counter. This is naturally satisfied by the counter only being updated inside the `for _ in range(max_steps)` body after `step_num` is incremented to at least `1`.

#### Scenario: Three consecutive no-tool-call responses trigger no_tool_call_repeat exit at step 3

- **GIVEN** a stub `LLMClient` that always returns `ChatResponse(content="...", tool_calls=[])` for every non-plan call (no `done`/`fail`/navigation tool)
- **AND** `loop()` is called with `max_steps=20`
- **WHEN** the loop runs
- **THEN** `RunResult.status` SHALL equal `"failed"`
- **AND** `RunResult.reason` SHALL equal `"no_tool_call_repeat"`
- **AND** `RunResult.steps` SHALL equal `3` (exits at step 3, not step 20)

#### Scenario: A periodic tool call between no-tool-call steps resets the counter and loop runs to timeout

- **GIVEN** a stub `LLMClient` that returns a `goto(url="http://example.com/<step>")` tool call on every 3rd step (steps 3, 6, 9, ...) and a no-tool-call response on the remaining steps
- **AND** `loop()` is called with `max_steps=20`
- **WHEN** the loop runs
- **THEN** the counter SHALL reset to `0` on each `goto` step (never accumulating 3 consecutive no-tool-call steps)
- **AND** `RunResult.status` SHALL equal `"timeout"` (runs to `max_steps` rather than failing via `no_tool_call_repeat`)
- **AND** `RunResult.steps` SHALL equal `20`

#### Scenario: No-tool-call exit fires before max_steps is exhausted

- **GIVEN** a stub `LLMClient` that always returns text-only responses with no tool calls
- **AND** `loop()` is called with `max_steps=20`
- **WHEN** the loop runs
- **THEN** `RunResult.steps` SHALL be less than `20`
- **AND** `RunResult.status` SHALL equal `"failed"`
- **AND** `RunResult.reason` SHALL equal `"no_tool_call_repeat"`

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

#### Scenario: budget_seconds appears in the loop signature

- **WHEN** `inspect.signature(agent.loop.loop).parameters` is read
- **THEN** the parameter list SHALL include `budget_seconds` as a keyword-only parameter with default `None`

### Requirement: Per-step phase latency breakdown

The system SHALL capture monotonic timestamps inside each iteration of `loop()` and write them under a `latency_breakdown_ms` key in every `step_breakdown` entry.

- `t0` (the existing per-step anchor used for `step_ms`) SHALL serve as the observation start.
- `t_llm_start` SHALL be captured immediately before `llm_client.chat(...)` is called.
- `t_dispatch_start` SHALL be captured immediately before the `for tool_call in response.tool_calls:` loop begins (or, when no tool calls are present, immediately before the no-tool-call branch is evaluated).
- `observation_ms` SHALL equal `int((t_llm_start - t0) * 1000)`.
- `llm_ms` SHALL equal `int((t_dispatch_start - t_llm_start) * 1000)`.
- `dispatch_ms` SHALL equal `int((time.monotonic() - t_dispatch_start) * 1000)` computed at the `_record_step` call site.
- The `latency_breakdown_ms` dict written into `step_breakdown[i]` SHALL have exactly the keys `observation_ms`, `llm_ms`, and `dispatch_ms`, all integers.
- The dict SHALL be present on every `step_breakdown` entry regardless of how the step exits (no-tool-call, `done`, `fail`, `stuck_repeat`, replan-exhaustion, max-steps). No entry SHALL have a missing or `null` `latency_breakdown_ms`.
- Sum invariant: `abs((observation_ms + llm_ms + dispatch_ms) - latency_ms) <= 5` SHALL hold for every step in a run, allowing ±5 ms for bookkeeping overhead.

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

### Requirement: Loop terminates early when N consecutive steps share an unchanged AX fingerprint and emit no successful action

`agent.loop.loop()` SHALL maintain a parallel rolling buffer `_no_progress_buf` of the last `_NO_PROGRESS_K` per-step tuples, alongside a module-level constant `_NO_PROGRESS_K = 4`. This buffer is entirely separate from the existing `_stuck_buf` (which tracks per-tool-call byte-identical repetition); both mechanisms run concurrently and whichever fires first wins.

At the end of each step's tool-call dispatch loop (after all tool calls in the LLM response have been dispatched and before `_record_step` is called for the normal step completion path), the loop SHALL:

- Capture the post-dispatch AX fingerprint by calling `observe.build_observation(browser, []).get("ax_fingerprint")`.
- Determine `any_action_succeeded: bool` — `True` iff at least one `click`, `type`, `goto`, or `read` tool call dispatched in this step returned a result string that does **not** start with `"Error:"`. `goto` and `read` are included alongside `click`/`type` because they represent observable progress: `goto` mutates URL/page state, and `read` retrieves information the LLM uses to make subsequent decisions. Excluding them produces false positives when the agent legitimately navigates and then explores via reads (the live smoke pattern: `goto example.com` step 1 → `read` body steps 2-N → `done` — fingerprint stays constant from step 1 onward).
- Append `(post_ax_fingerprint, any_action_succeeded)` to `_no_progress_buf`.
- Trim `_no_progress_buf` to the last `_NO_PROGRESS_K` entries (remove from the front if over length).
- Check: if `len(_no_progress_buf) == _NO_PROGRESS_K` AND all entries share the same fingerprint AND all entries have `any_action_succeeded == False`, then call `_record_step(...)` and return `RunResult(status="failed", reason="no_progress", result=None, evidence=None, verifier=None, steps=step_num, prompt_tokens=cum_prompt_tokens, completion_tokens=cum_completion_tokens, usd=cum_usd, latency_ms_total=sum(latency_ms_per_step), latency_ms_per_step=latency_ms_per_step, step_breakdown=step_breakdown)`.

`_no_progress_buf` SHALL be initialized to `[]` at the start of `loop()` and SHALL NOT be reset between steps. It SHALL NOT be reset on L1→L2 supervisor escalations (unlike `_stuck_buf`) — supervisor-mediated outcomes are already reflected in `any_action_succeeded`. It SHALL be cleared when a `replan` is triggered (i.e. when the supervisor policy is `"halt"` and `replan_used` is `False`), because `replan` constitutes a strategy reset that invalidates the prior observation window; this is distinct from a simple L1→L2 escalation.

The `_no_progress_buf` check SHALL run only on steps where the tool-call loop completed without an earlier `_stuck_buf` bail. It SHALL NOT run on steps with no tool calls (those are handled by `_consecutive_no_tool_call_steps`).

The `latency_breakdown_ms` dict MUST be present on the bailing step's record (the existing `_record_step` call handles this via `_phase_breakdown`).

#### Scenario: Constant fingerprint with no successful click, type, goto, or read exits at step 4 with reason no_progress

- **GIVEN** a stub `LLMClient` that emits `read({"intent": f"x{i}"})` on each step (different args each step, so `_stuck_buf` never fills)
- **AND** a stub `Browser` whose `build_observation()` always returns the same `ax_fingerprint` (constant hash)
- **AND** the `read` tool dispatch returns an error string each step (locator missed, intent unmatched)
- **AND** `loop()` is called with `max_steps=20`
- **WHEN** the loop runs
- **THEN** `RunResult.status` SHALL equal `"failed"`
- **AND** `RunResult.reason` SHALL equal `"no_progress"`
- **AND** `RunResult.steps` SHALL equal `4` (bails at step 4, not step 20)

#### Scenario: Alternating fingerprint prevents no_progress detection and loop runs to max_steps

- **GIVEN** a stub `LLMClient` that emits `read({"intent": f"x{i}"})` on each step
- **AND** a stub `Browser` whose `build_observation()` alternates between two distinct `ax_fingerprint` values on successive calls (e.g. `"aaaa"` on even steps, `"bbbb"` on odd steps)
- **AND** `loop()` is called with `max_steps=6`
- **WHEN** the loop runs
- **THEN** `RunResult.status` SHALL NOT equal `"failed"` with `reason="no_progress"` (the buffer never fills with a uniform fingerprint)
- **AND** the loop SHALL run until another termination condition fires (e.g. `max_steps` or `no_tool_call_repeat`)

#### Scenario: Constant fingerprint but click returned ok does not trigger no_progress bail

- **GIVEN** a stub `LLMClient` that emits a `click({"intent": "button"})` tool call on every step
- **AND** a stub `Browser` whose `build_observation()` always returns the same `ax_fingerprint`
- **AND** the `click` dispatch always returns `"Clicked 'button' (ok)"` (outcome `ok`, non-error string)
- **AND** `loop()` is called with `max_steps=20`
- **WHEN** the loop runs
- **THEN** `RunResult.reason` SHALL NOT equal `"no_progress"` (each step has `any_action_succeeded=True`, so the buffer never satisfies the bail condition)

#### Scenario: no_progress exit emits a complete step record with latency_breakdown_ms

- **GIVEN** a stub setup that triggers the no_progress exit condition at step 4
- **WHEN** `RunResult` is returned with `reason="no_progress"`
- **THEN** `RunResult.step_breakdown` SHALL have exactly `4` entries
- **AND** every entry in `step_breakdown` SHALL have a `latency_breakdown_ms` key with integer fields `observation_ms`, `llm_ms`, and `dispatch_ms`

#### Scenario: replan clears the no_progress buffer so post-replan steps start a fresh window

- **GIVEN** a run that has accumulated some entries in `_no_progress_buf` (but fewer than `_NO_PROGRESS_K`)
- **AND** the supervisor triggers a `replan` (policy `"halt"`, `replan_used == False`)
- **WHEN** the replan completes and execution continues
- **THEN** `_no_progress_buf` SHALL be empty and the no_progress bail counter starts fresh from zero

#### Scenario: existing stuck_repeat test is unaffected by no_progress buffer

- **GIVEN** a stub `LLMClient` that always returns `goto(url="about:blank")` (same tool call with identical args each step)
- **AND** `loop()` is called with `max_steps=20`
- **WHEN** the loop runs
- **THEN** `RunResult.reason` SHALL equal `"stuck_repeat"` (fires at step 3 via `_stuck_buf`, before `_no_progress_buf` can accumulate 4 entries)
- **AND** `RunResult.steps` SHALL equal `3`
