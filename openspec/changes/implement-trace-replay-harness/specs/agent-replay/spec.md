## ADDED Requirements

### Requirement: ReplayDivergence dataclass

The system SHALL provide `agent.replay.ReplayDivergence` — a frozen dataclass representing a single step where the replayed decision differed from the recorded one. It SHALL have:

- `step_id: str | None` — the `step_id` from the corresponding recorded `DecisionEvent`; `None` if the recorded event had no `step_id`.
- `expected: dict` — the recorded decision, with keys `tool: str` and `args: dict`.
- `actual: dict` — the replayed decision, with keys `tool: str` and `args: dict`.

`ReplayDivergence` SHALL be frozen (immutable after construction).

#### Scenario: ReplayDivergence is constructible and frozen

- **WHEN** code constructs `ReplayDivergence(step_id="s1", expected={"tool": "goto", "args": {"url": "http://a"}}, actual={"tool": "read", "args": {}})`
- **THEN** construction SHALL succeed
- **AND** attempting to assign to any field SHALL raise `dataclasses.FrozenInstanceError`

### Requirement: ReplayResult dataclass

The system SHALL provide `agent.replay.ReplayResult` — a frozen dataclass summarising the outcome of a replay run. It SHALL have:

- `matched: bool` — `True` if every replayed decision matches the recording; `False` if any divergence was detected or the call counts differ.
- `steps: int` — number of decision steps compared (minimum of recorded count and replayed count).
- `first_divergence: ReplayDivergence | None` — the first step where recorded and replayed decisions differ; `None` when `matched` is `True`.

`ReplayResult` SHALL be frozen.

#### Scenario: ReplayResult matched is True when all decisions agree

- **GIVEN** a recorded trace with two `DecisionEvent`s (tool=`goto`, tool=`done`)
- **AND** the replay produces the same two decisions in the same order with identical `tool` and `args`
- **WHEN** `replay_run(trace_path)` returns
- **THEN** `result.matched` SHALL be `True`
- **AND** `result.first_divergence` SHALL be `None`
- **AND** `result.steps` SHALL equal `2`

#### Scenario: ReplayResult matched is False when a decision diverges

- **GIVEN** a recorded trace with `DecisionEvent(tool="goto", args={"url": "http://x"})` at step 1
- **AND** the LLM stub (fed the recorded response) would return that same response, but the trace fixture has been mutated so the recorded `DecisionEvent.tool` is changed to `"read"`
- **WHEN** `replay_run(trace_path)` is called with the mutated fixture
- **THEN** `result.matched` SHALL be `False`
- **AND** `result.first_divergence` SHALL be a `ReplayDivergence` with `expected["tool"] == "read"` and `actual["tool"] == "goto"`

#### Scenario: ReplayResult is frozen

- **WHEN** a `ReplayResult` instance is constructed
- **THEN** attempting to assign to any field SHALL raise `dataclasses.FrozenInstanceError`

### Requirement: replay_run function

The system SHALL provide `agent.replay.replay_run(trace_path: str | Path) -> ReplayResult` — a function that:

1. Reads the JSONL file at `trace_path`. The first line SHALL be parsed as a `Run` object via `Run.model_validate_json(line)`. Subsequent lines SHALL be parsed as `AnyEvent` objects via `TypeAdapter(AnyEvent).validate_json(line)`.
2. Extracts the recorded `DecisionEvent` list (filtered from the event stream, ordered by `seq`).
3. Extracts the recorded `LLMCallEvent` list with `purpose == "decide"` (ordered by `seq`) and converts each `LLMCallEvent.response` dict to a `ChatResponse` object.
4. Constructs a `StubBrowser` and a `StubLLMClient` loaded with the recorded `ChatResponse` sequence.
5. Calls `agent.loop.loop(task=run.task, browser=stub_browser, llm_client=stub_llm, max_steps=len(recorded_decisions) + 2)`.
6. After `loop()` returns, compares the tool call each `chat()` invocation returned (from `stub_llm.responses_consumed`) against the corresponding recorded `DecisionEvent`. Comparison is on `tool` (string) and `args` (dict shallow equality).
7. If all counts match and all (`tool`, `args`) pairs are equal, returns `ReplayResult(matched=True, steps=N, first_divergence=None)`.
8. If counts differ or any pair diverges, returns `ReplayResult(matched=False, steps=min(recorded, replayed), first_divergence=<first mismatch>)`.

The function SHALL NOT make any HTTP calls, SHALL NOT launch a Playwright browser process, and SHALL NOT read `LLM_BASE_URL` or `LLM_MODEL` environment variables.

#### Scenario: replay_run loads a valid fixture without error

- **GIVEN** the fixture file `task2/tests/fixtures/traces/simple_goto_done.jsonl` exists and is valid
- **WHEN** `replay_run(fixture_path)` is called
- **THEN** it SHALL return a `ReplayResult` without raising

#### Scenario: replay_run returns matched=True for an unmodified fixture

- **GIVEN** the unmodified `simple_goto_done.jsonl` fixture
- **WHEN** `replay_run(fixture_path)` is called
- **THEN** `result.matched` SHALL be `True`
- **AND** `result.first_divergence` SHALL be `None`

#### Scenario: replay_run returns matched=False and first_divergence for a mutated fixture

- **GIVEN** a copy of `simple_goto_done.jsonl` with the first `DecisionEvent.tool` changed from `"goto"` to `"read"`
- **WHEN** `replay_run(mutated_path)` is called
- **THEN** `result.matched` SHALL be `False`
- **AND** `result.first_divergence` SHALL NOT be `None`
- **AND** `result.first_divergence.expected["tool"]` SHALL equal `"read"`
- **AND** `result.first_divergence.actual["tool"]` SHALL equal `"goto"`

#### Scenario: replay_run does not launch a browser or call a live LLM

- **GIVEN** no Playwright installation and no reachable LLM endpoint
- **WHEN** `replay_run(fixture_path)` is called
- **THEN** it SHALL return without raising `playwright` import errors or HTTP connection errors

### Requirement: StubBrowser

The system SHALL provide `agent.replay.StubBrowser` — a class that satisfies the duck-type contract `loop.py` relies on for `agent.browser.Browser`. It SHALL:

- Expose a `_page` attribute set to an inner `_StubPage` instance whose `.url` property returns `"http://stub.local/"` and whose `.evaluate(js)` method returns `""`.
- Implement `goto(url: str) -> None` as a no-op.
- Implement `read(selector: str) -> str` returning `""`.
- Implement `screenshot(*, full_page: bool = False) -> bytes` returning `b""`.
- Implement `click_at(x: int, y: int) -> None` as a no-op.
- NOT subclass `agent.browser.Browser` (to avoid pulling in Playwright).
- Support use as a context manager (`__enter__` returns `self`, `__exit__` is a no-op).

#### Scenario: StubBrowser._page provides url and evaluate

- **WHEN** `stub = StubBrowser()` is constructed
- **THEN** `stub._page.url` SHALL return a non-empty string
- **AND** `stub._page.evaluate("() => document.body.innerText")` SHALL return a string (may be empty)

#### Scenario: StubBrowser.goto is a no-op

- **WHEN** `stub.goto("http://example.com")` is called
- **THEN** it SHALL return without raising

#### Scenario: StubBrowser does not import playwright

- **WHEN** `from agent.replay import StubBrowser` is executed in an environment where `playwright` is not installed
- **THEN** the import SHALL NOT raise `ModuleNotFoundError` for playwright

### Requirement: StubLLMClient

The system SHALL provide `agent.replay.StubLLMClient` — a class that satisfies the duck-type contract `loop.py` relies on for `agent.llm.LLMClient`. It SHALL:

- Accept a `responses: list[ChatResponse]` in `__init__`.
- Expose a `responses_consumed: list[ChatResponse]` attribute that records each `ChatResponse` returned by `chat()` in call order.
- In `chat(messages, *, tools=None, **kwargs) -> ChatResponse`: pop and return the next `ChatResponse` from `responses`; if the list is exhausted, return a no-op `ChatResponse(content=None, tool_calls=[], finish_reason="stop", model="stub", usage=Usage(0,0,0), raw={})`.
- Append each returned `ChatResponse` to `responses_consumed` before returning.
- NOT subclass `agent.llm.LLMClient` (to avoid creating an HTTP client or reading env vars).

#### Scenario: StubLLMClient returns responses in order

- **GIVEN** a `StubLLMClient` constructed with two `ChatResponse` objects `[r1, r2]`
- **WHEN** `chat(...)` is called twice
- **THEN** the first call SHALL return `r1` and the second SHALL return `r2`
- **AND** `stub.responses_consumed` SHALL equal `[r1, r2]`

#### Scenario: StubLLMClient returns no-op response when exhausted

- **GIVEN** a `StubLLMClient` constructed with one `ChatResponse`
- **WHEN** `chat(...)` is called twice
- **THEN** the second call SHALL return a `ChatResponse` with an empty `tool_calls` list and `finish_reason="stop"`
- **AND** SHALL NOT raise

### Requirement: Fixture JSONL for replay tests

The system SHALL include a hand-authored fixture file at `task2/tests/fixtures/traces/simple_goto_done.jsonl`. The file SHALL:

- Have its first line be a valid `Run` JSON object (parseable by `Run.model_validate_json`).
- Have subsequent lines be valid `AnyEvent` JSON objects (parseable by `TypeAdapter(AnyEvent).validate_json`) with strictly increasing `seq`.
- Contain at minimum: one `ObservationEvent`, one `LLMCallEvent` with `purpose="decide"` whose `response` encodes a `goto` tool call, one `DecisionEvent` with `tool="goto"`, one second `ObservationEvent`, one second `LLMCallEvent` with `purpose="decide"` whose `response` encodes a `done` tool call, and one second `DecisionEvent` with `tool="done"`.
- NOT depend on any live browser or LLM run.

#### Scenario: Fixture parses without validation errors

- **WHEN** the first line of `simple_goto_done.jsonl` is parsed via `Run.model_validate_json(line)`
- **THEN** it SHALL produce a valid `Run` object without raising `pydantic.ValidationError`
- **WHEN** each subsequent line is parsed via `TypeAdapter(AnyEvent).validate_json(line)`
- **THEN** each SHALL produce a concrete event subtype without raising

#### Scenario: Fixture contains expected event kinds in order

- **WHEN** `simple_goto_done.jsonl` is parsed
- **THEN** the event sequence SHALL include at least one `ObservationEvent`, two `LLMCallEvent`s with `purpose="decide"`, and two `DecisionEvent`s
- **AND** the first `DecisionEvent.tool` SHALL equal `"goto"`
- **AND** the second `DecisionEvent.tool` SHALL equal `"done"`
