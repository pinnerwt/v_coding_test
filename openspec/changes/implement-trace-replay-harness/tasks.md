## 1. Red — Failing tests (fixture + test scaffold)

- [ ] 1.1 Create directory `task2/tests/fixtures/traces/` (no `__init__.py` needed — it's a data directory).
- [ ] 1.2 Author `task2/tests/fixtures/traces/simple_goto_done.jsonl`. Line 1: a valid `Run` JSON with `status=None`, `ended_at=None`, `final=None`, `totals=None`, `task="go to example and return title"`. Lines 2–7: `ObservationEvent(seq=1)`, `LLMCallEvent(seq=2, purpose="decide", response={"tool_calls": [{"id": "tc-1", "type": "function", "function": {"name": "goto", "arguments": "{\"url\": \"http://stub.local/\"}"}}], "content": null, "finish_reason": "tool_calls"})`, `DecisionEvent(seq=3, tool="goto", args={"url": "http://stub.local/"})`, `ObservationEvent(seq=4)`, `LLMCallEvent(seq=5, purpose="decide", response={"tool_calls": [{"id": "tc-2", "type": "function", "function": {"name": "done", "arguments": "{\"result\": {\"title\": \"Stub\"}, \"evidence\": {\"url\": \"http://stub.local/\", \"text_snippet\": \"Stub\"}}"}}], "content": null, "finish_reason": "tool_calls"})`, `DecisionEvent(seq=6, tool="done", args={"result": {"title": "Stub"}, "evidence": {"url": "http://stub.local/", "text_snippet": "Stub"}})`. All events share the same `run_id` as the `Run` header.
- [ ] 1.3 Create `task2/tests/agent/test_replay.py`. Add `from agent.replay import ReplayDivergence, ReplayResult, StubBrowser, StubLLMClient, replay_run`. This import will fail (`ModuleNotFoundError`) until `replay.py` exists — that is the first red bar. Do NOT proceed past this step until you have confirmed the import fails.
- [ ] 1.4 Add `test_replay_divergence_is_frozen`: construct a `ReplayDivergence`; assert `FrozenInstanceError` on field assignment.
- [ ] 1.5 Add `test_replay_result_is_frozen`: construct a `ReplayResult`; assert `FrozenInstanceError` on field assignment.
- [ ] 1.6 Add `test_stub_browser_page_attributes`: instantiate `StubBrowser()`; assert `stub._page.url` is a non-empty string; assert `stub._page.evaluate("() => document.body.innerText")` returns a string.
- [ ] 1.7 Add `test_stub_browser_goto_noop`: call `stub.goto("http://example.com")`; assert no exception raised.
- [ ] 1.8 Add `test_stub_llm_client_returns_in_order`: construct a `StubLLMClient([r1, r2])` with two dummy `ChatResponse` objects; call `chat({})` twice; assert first call returns `r1`, second returns `r2`; assert `stub.responses_consumed == [r1, r2]`.
- [ ] 1.9 Add `test_stub_llm_client_exhausted_returns_noop`: construct a `StubLLMClient([r1])`; call `chat({})` twice; assert second call returns a `ChatResponse` with `tool_calls == []` and `finish_reason == "stop"` without raising.
- [ ] 1.10 Add `test_fixture_parses_without_error`: load `simple_goto_done.jsonl`, parse line 1 via `Run.model_validate_json`, parse remaining lines via `TypeAdapter(AnyEvent).validate_json`; assert no `ValidationError` is raised.
- [ ] 1.11 Add `test_fixture_event_sequence`: parse the fixture; assert the event list contains at least one `ObservationEvent`, two `LLMCallEvent`s with `purpose == "decide"`, and two `DecisionEvent`s; assert `decisions[0].tool == "goto"` and `decisions[1].tool == "done"`.
- [ ] 1.12 Add `test_replay_run_matched_on_unmodified_fixture`: call `replay_run(FIXTURE_PATH)` where `FIXTURE_PATH` is the absolute path to `simple_goto_done.jsonl`; assert `result.matched is True` and `result.first_divergence is None`.
- [ ] 1.13 Add `test_replay_run_divergence_on_mutated_fixture`: write a temp file that is a copy of `simple_goto_done.jsonl` with the first `DecisionEvent` line's `"tool"` changed from `"goto"` to `"read"`; call `replay_run(tmp_path)`; assert `result.matched is False`; assert `result.first_divergence.expected["tool"] == "read"` and `result.first_divergence.actual["tool"] == "goto"`.
- [ ] 1.14 From `task2/`, run `uv run pytest tests/agent/test_replay.py -x` and confirm all tests fail with `ModuleNotFoundError: No module named 'agent.replay'`.

## 2. Green — Implement `agent/replay.py`

- [ ] 2.1 Create `task2/agent/replay.py` with `from __future__ import annotations`, stdlib imports (`dataclasses`, `json`, `pathlib`), and imports from `agent.trace` (`Run`, `AnyEvent`, `DecisionEvent`, `LLMCallEvent`, `TypeAdapter`), `agent.llm` (`ChatResponse`, `ToolCall`, `Usage`), and `agent.loop` (`loop`).
- [ ] 2.2 Define the inner `_StubPage` class with `.url: str` (returns `"http://stub.local/"`) and `.evaluate(js: str) -> str` (returns `""`).
- [ ] 2.3 Define `StubBrowser` with `_page = _StubPage()`, `goto` (no-op), `read` (returns `""`), `screenshot` (returns `b""`), `click_at` (no-op), `__enter__` (returns `self`), `__exit__` (no-op). Do NOT subclass `agent.browser.Browser`.
- [ ] 2.4 Define `StubLLMClient` with `__init__(responses: list[ChatResponse])`, `responses_consumed: list[ChatResponse] = []`, and `chat(messages, *, tools=None, **kwargs) -> ChatResponse` that pops from `_remaining` and appends to `responses_consumed`; returns the no-op response when exhausted. Do NOT subclass `agent.llm.LLMClient`.
- [ ] 2.5 Define `_noop_response() -> ChatResponse` helper that returns `ChatResponse(content=None, tool_calls=[], finish_reason="stop", model="stub", usage=Usage(0,0,0), raw={})`.
- [ ] 2.6 Define `_response_from_recorded(resp: dict) -> ChatResponse` helper that converts a recorded `LLMCallEvent.response` dict to a `ChatResponse`. Parse `resp["tool_calls"]` (if present) into `list[ToolCall]`; set `content`, `finish_reason`, `model="stub"`, `usage=Usage(0,0,0)`, `raw=resp`.
- [ ] 2.7 Define the frozen dataclass `ReplayDivergence(step_id, expected, actual)`.
- [ ] 2.8 Define the frozen dataclass `ReplayResult(matched, steps, first_divergence)`.
- [ ] 2.9 Define `replay_run(trace_path: str | Path) -> ReplayResult`:
  - Read all lines from `trace_path`.
  - Parse line 0 as `Run`; parse lines 1+ as `AnyEvent` via `_any_event_adapter`.
  - Extract `recorded_decisions: list[DecisionEvent]` (kind == `"decision"`, sorted by `seq`).
  - Extract `decide_llm_calls: list[LLMCallEvent]` (kind == `"llm_call"` and `purpose == "decide"`, sorted by `seq`).
  - Convert each `decide_llm_calls[i].response` to `ChatResponse` via `_response_from_recorded`.
  - Construct `stub_browser = StubBrowser()` and `stub_llm = StubLLMClient(responses)`.
  - Call `loop(task=run.task, browser=stub_browser, llm_client=stub_llm, max_steps=len(recorded_decisions) + 2)`.
  - Collect replayed decisions from `stub_llm.responses_consumed`: for each consumed `ChatResponse`, extract `tool_calls[0]` (if any) to get `(tool_name, args)`.
  - Compare replayed `(tool, args)` pairs against `(recorded_decisions[i].tool, recorded_decisions[i].args)` for `i` in `range(min(len(recorded_decisions), len(replayed)))`.
  - On first mismatch or count mismatch, return `ReplayResult(matched=False, steps=..., first_divergence=ReplayDivergence(...))`.
  - If all match, return `ReplayResult(matched=True, steps=len(recorded_decisions), first_divergence=None)`.
- [ ] 2.10 From `task2/`, run `uv run pytest tests/agent/test_replay.py -x` and confirm all tests pass.

## 3. Full test suite (green bar)

- [ ] 3.1 From `task2/`, run `uv run pytest` (full suite) and confirm all previously-passing tests still pass — no regressions introduced by `replay.py`.

## 4. Lint and format

- [ ] 4.1 From `task2/`, run `uv run ruff check --fix .` to auto-fix any lint errors introduced by `replay.py` and `test_replay.py`.
- [ ] 4.2 From `task2/`, run `uv run ruff format .` to auto-format changed files.
- [ ] 4.3 From `task2/`, run `uv run ruff check .` and confirm it exits clean (zero errors, zero warnings).

## 5. Refactor under green (if needed)

- [ ] 5.1 Review `replay_run` for edge cases: empty trace (no decision events), trace with only one decision. Add minimal test coverage if these paths are untested and refactor only while tests remain green.
- [ ] 5.2 Verify that `StubBrowser` and `StubLLMClient` have no imports from `playwright` or `httpx` (confirm with `grep -n "playwright\|httpx" task2/agent/replay.py`).
- [ ] 5.3 Verify `replay.py` has no hardcoded `LLM_BASE_URL` or `LLM_MODEL` references (`grep -n "LLM_BASE_URL\|LLM_MODEL\|localhost:8090" task2/agent/replay.py` returns nothing).
