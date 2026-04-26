## Context

Tickets #1–#12 deliver a working agent loop with a structured append-only trace. Ticket #12 (`trace.py`) stores every `ObservationEvent`, `LLMCallEvent`, and `DecisionEvent` to SQLite JSONL. Ticket #13 (this change) builds the regression harness on top: load that recording, drive `loop.py` offline, and assert the new decision sequence matches. The immediate audience is any developer who modifies `loop.py` or the agent's system prompt — they need to know, before merging, whether the change alters the agent's decision behaviour on runs it previously handled correctly.

Constraints from `CLAUDE.md` and `plan.md`:
- No hardcoded LLM endpoint; `replay.py` must not construct a real `LLMClient` or launch Playwright.
- TDD: tests are written first (red), then the module (green).
- `uv run pytest`, `uv run ruff check .` from `task2/`.
- The fixture JSONL must be hand-authored — it cannot depend on a live browser run.

## Goals / Non-Goals

**Goals:**

- Load a `Run` + ordered `AnyEvent` list from a JSONL file (one JSON object per line, same format `TraceWriter` already writes).
- Drive `loop.py` offline: stub both the browser tool surface and the LLM client so no network or Playwright is needed.
- The LLM stub returns the recorded `LLMCallEvent.response` for each `chat()` call in sequential order; the browser stub is a silent no-op (goto/read/screenshot/click_at return canned strings or `b""`).
- Collect the `DecisionEvent`s emitted by the new run and diff them against the recorded ones: compare `tool` and `args` per step.
- Return a `ReplayResult` dataclass: `matched: bool`, `steps: int`, `first_divergence: ReplayDivergence | None`. `ReplayDivergence` carries `step_id`, `expected: dict` (`{tool, args}`), `actual: dict` (`{tool, args}`).
- The harness is a pure Python module with no new dependencies.
- A hand-authored JSONL fixture under `task2/tests/fixtures/traces/` covers the test surface without needing a live run.

**Non-Goals:**

- LLM-side replay (re-sending the recorded `LLMCallEvent.prompt` to a live model and checking response divergence) — that is a separate concern described in `plan.md` but not part of this ticket.
- Locator replay (`LocateEvent.candidates` + `chosen` re-ranking) — deferred.
- Visual replay (screenshot scrubbing) — deferred.
- Integration with the HTTP API or `api/server.py` — that is ticket #14.
- Full production wiring of `TraceWriter` into `loop.py` — that is separate from the harness.
- Replaying `click`, `type`, `select`, `wait_for`, `back` browser actions — the current `loop.py` only exposes `goto`, `read`, `done`, `fail`; the stub covers the same surface.

## Decisions

### Decision 1: Fixture format — hand-authored JSONL, not a live-captured trace

The fixture is a plain JSONL file where each line is a JSON object parseable by `TypeAdapter(AnyEvent).validate_json(line)` (the discriminated union already in `trace.py`). The first line is a `Run` object (parsed separately by `Run.model_validate_json`). This matches exactly what `TraceWriter` writes.

**Why hand-authored**: the harness test must not depend on a live browser or live LLM. A hand-authored fixture is deterministic, committed, and readable — reviewers can verify correctness by inspection. The fixture is minimal: a `Run` header, one `ObservationEvent`, one `LLMCallEvent` (purpose `"decide"`, response containing a `goto` tool call), one `DecisionEvent`, a second `ObservationEvent`, a second `LLMCallEvent` (response containing a `done` tool call), and a second `DecisionEvent`.

**Alternative**: capture a trace from the existing happy-path test fixture and snapshot it. Rejected because the snapshot would be brittle to changes in `loop.py`'s message format and would re-introduce a live-browser dependency in the test setup.

### Decision 2: `StubBrowser` — replaces `agent.browser.Browser` in replay

`StubBrowser` is a plain Python class with the same method surface as `Browser` (`goto`, `read`, `screenshot`, `click_at`) and the same `_page` attribute (set to a sentinel object so `_observe(browser)` in `loop.py` does not return `{"url": "", "text": ""}`). `goto` is a no-op; `read` returns `""` (an empty string is sufficient — the LLM response is already canned by the stub); `screenshot` returns `b""`.

`StubBrowser` does NOT subclass `Browser` to avoid pulling in Playwright. It satisfies the duck-type contract that `loop.py` relies on.

**Alternative**: mock `browser._page` with `unittest.mock.MagicMock`. Rejected because `loop.py` calls `page.url` and `page.evaluate(...)` directly on `browser._page`, and MagicMock returns MagicMock objects for all attribute accesses — the observation dict would contain non-string values that could confuse the LLM message format. A purpose-built `StubPage` (an inner class of `StubBrowser`) is cleaner.

### Decision 3: `StubLLMClient` — returns recorded responses in order

`StubLLMClient.__init__` accepts a list of `ChatResponse` objects built from the recorded `LLMCallEvent.response` fields. Each `chat()` call pops the next response from the list and returns it. When the list is exhausted, a no-op `ChatResponse` (no tool calls, `finish_reason="stop"`) is returned to allow the loop to time out gracefully rather than raise `IndexError`.

The conversion from `LLMCallEvent.response: dict` to `ChatResponse` is handled by `replay.py`'s `_response_from_recorded(resp: dict) -> ChatResponse` helper, which mirrors `agent.llm._parse_response` but operates on the already-decoded dict rather than raw HTTP.

**Alternative**: monkey-patch `llm.LLMClient.chat` with `unittest.mock.patch`. Rejected because patch leaks between tests if a test fails mid-execution, and it requires importing `httpx` transitively. An explicit stub is self-contained and visible.

### Decision 4: Replay loop drives `agent.loop.loop()` directly

`replay_run(trace_path: str | Path) -> ReplayResult` loads the JSONL, extracts the recorded `DecisionEvent` sequence (in `seq` order), constructs `StubBrowser` and `StubLLMClient`, and calls `loop(task, stub_browser, stub_llm_client, max_steps=len(recorded_decisions) + 2)`. After `loop()` returns, `replay_run` inspects the decisions the stub LLM client was asked to provide (it records each `chat()` call's incoming message list and its returned response), then compares the `tool` + `args` fields of each resulting terminal/non-terminal tool call.

**Challenge**: `loop.py` does not currently emit `DecisionEvent` objects — it just calls the browser. The replay harness cannot intercept decisions from inside `loop.py` without modifying it. 

**Resolution**: the `StubLLMClient` records which `ChatResponse` it returned per call, and the replay harness can correlate the recorded `LLMCallEvent` sequence (which already has `response.tool_calls`) to the responses the stub returned. The harness's assertion is therefore: for call index `i`, the stub returned a response whose `tool_calls[0].name` and `args` must match the recorded `DecisionEvent` at position `i`. If they diverge, it means `loop.py` passed a different message list to `chat()` for call `i` than it did during the original run — which is the regression signal we want to capture.

Concretely: after running offline, the harness compares `stub_llm.responses_consumed[i]` (the `ChatResponse` the stub returned at step `i`) against `recorded_decisions[i]` (the `DecisionEvent` from the JSONL). Since the stub faithfully returns the recorded response, a mismatch at the `DecisionEvent` level would only occur if `loop.py`'s prompt construction or tool dispatch is broken. For the current scope, the harness verifies that `loop.py` consumed the same number of LLM calls and each returned response's primary tool call matches the recorded `DecisionEvent.tool` and `DecisionEvent.args`.

**Simpler alternative** for MVP: compare only the sequence length and each LLM call's returned `tool` name. Accepted — `args` comparison is included (shallow dict equality) to catch argument regressions too.

### Decision 5: `replay_run` API surface

```python
@dataclass(frozen=True)
class ReplayDivergence:
    step_id: str | None
    expected: dict  # {"tool": str, "args": dict}
    actual: dict    # {"tool": str, "args": dict}

@dataclass(frozen=True)
class ReplayResult:
    matched: bool
    steps: int
    first_divergence: ReplayDivergence | None

def replay_run(trace_path: str | Path) -> ReplayResult: ...
```

`trace_path` is a path to a JSONL file. First line is the `Run` JSON; subsequent lines are `AnyEvent` JSON. The function reads all lines, filters to `DecisionEvent` and `LLMCallEvent` kinds, reconstructs `ChatResponse` objects, drives the loop, and returns `ReplayResult`.

**Why a file path rather than a `Run` + events list**: the primary use case is "I have a trace file on disk" (which is what `TraceWriter` produces). The function can be trivially wrapped later to accept a SQLite `run_id`. Keeping it file-first avoids pulling in SQLite in the test code.

### Decision 6: Fixture JSONL location

`task2/tests/fixtures/traces/simple_goto_done.jsonl` — a subdirectory `traces/` under the existing `fixtures/` directory keeps trace fixtures separate from HTML fixtures and is consistent with the naming used in `plan.md` ("small built-in catalog").

### Decision 7: `replay.py` location

`task2/agent/replay.py` — collocated with `loop.py`, `trace.py`, `llm.py`. It is an agent-level module, not a test utility, because in a future ticket it will be callable from the HTTP API or CLI (`GET /tasks/{run_id}/replay`). Keeping it under `agent/` preserves that path.

## Risks / Trade-offs

- **`loop.py` prompt format drift**: if a future change to `loop.py`'s message construction causes the loop to make a *different number* of LLM calls for the same observations, the harness will report a divergence in call count, not just args. This is the intended behaviour — it surfaces regressions. Developers will need to update the fixture JSONL when intentionally changing the loop's LLM call cadence.
- **Fixture maintenance cost**: hand-authored JSONL must be kept in sync with `trace.py`'s Pydantic models. If a field is added or renamed in a model, the fixture will fail `validate_json()` at load time. This is caught immediately at test time and is preferable to silently replaying against a stale schema.
- **`StubBrowser._page` sentinel**: `loop.py` accesses `browser._page.url` and `browser._page.evaluate(...)` directly. The stub's inner `_StubPage` must implement both. If `loop.py` adds new `_page` attribute accesses in a future ticket, the `StubPage` will need updating.
- **`args` equality is shallow**: `json.loads(tool_call.arguments)` vs recorded `DecisionEvent.args` are compared with `==`. If the LLM produces float values that serialize differently (e.g. `1.0` vs `1`), the comparison may produce false positives. For the current MVP (goto URL strings and done dicts), this is not a practical concern.

## Open Questions

(none — all decisions resolved above)
