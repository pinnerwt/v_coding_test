## Why

Ticket #12 introduced `trace.py` — a structured, append-only record of every run. Now that recordings exist, there is no way to verify that changes to `loop.py` or the agent's prompts don't silently regress its decision behaviour on known-good historical runs. This change introduces a **decision replay harness**: given a recorded trace, drive `loop.py` against a stubbed browser (no real Playwright, no real LLM) using the stored `ObservationEvent` observations, and assert that the new `DecisionEvent`s match the recorded ones. Any divergence in `tool` or `args` at any step surfaces immediately — before the change reaches production.

## What Changes

- New module `task2/agent/replay.py`: loads a recorded trace (JSONL lines from SQLite or a file path), rebuilds the ordered `ObservationEvent` / `LLMCallEvent` / `DecisionEvent` sequences, drives `loop.py` offline with a stub browser and stub LLM client, collects emitted `DecisionEvent`s, and returns a `ReplayResult` dataclass describing match vs. divergence.
- `ReplayResult` dataclass: `matched: bool`, `steps: int`, `first_divergence: ReplayDivergence | None` where `ReplayDivergence` carries `step_id`, `expected` (`{tool, args}`), and `actual` (`{tool, args}`).
- `StubBrowser`: a drop-in replacement for `agent.browser.Browser` whose `goto`, `read`, `screenshot`, `click_at` methods are no-ops or return canned strings. Does not launch Playwright.
- `StubLLMClient`: a drop-in replacement for `agent.llm.LLMClient` that, for each `chat()` call in sequence, returns the corresponding recorded `LLMCallEvent.response` converted to a `ChatResponse`.
- New fixture JSONL file `task2/tests/fixtures/traces/simple_goto_done.jsonl`: a minimal hand-authored trace (one `ObservationEvent` → one `LLMCallEvent` with `goto` decision → one `DecisionEvent` → one final `ObservationEvent` → one `LLMCallEvent` with `done` decision → one `DecisionEvent`). This fixture is the test surface and does not depend on a live browser run.
- New test file `task2/tests/agent/test_replay.py`: TDD-first tests covering: fixture loads cleanly; matched replay returns `ReplayResult(matched=True)`; mutated fixture (tool changed from `goto` to `read`) triggers `ReplayResult(matched=False, first_divergence=...)` with correct step metadata.
- No changes to `loop.py`, `trace.py`, `llm.py`, or `browser.py` production code. The harness is purely additive.

## Capabilities

### New Capabilities

- `agent-replay`: Offline decision-replay harness. Given a recorded `Run` + `Event` JSONL, drive `loop.py` with stubbed browser and LLM, collect emitted `DecisionEvent`s, and diff against the recording. Reports first divergence (step_id, expected tool+args, actual tool+args).

### Modified Capabilities

(none — no existing spec-level requirements change)

## Impact

- **Code**: new `task2/agent/replay.py`; new `task2/tests/agent/test_replay.py`; new `task2/tests/fixtures/traces/simple_goto_done.jsonl`.
- **Dependencies**: none new. `replay.py` uses only `agent.trace` (already in `task2/`), `agent.loop` (already in `task2/`), `agent.llm.ChatResponse` / `ToolCall` / `Usage` (already in `task2/`), and stdlib (`json`, `dataclasses`, `pathlib`).
- **Existing modules**: `loop.py`, `trace.py`, `llm.py`, `browser.py`, `locate.py`, `supervisor.py` are all unchanged.
- **Test tooling**: `uv run pytest task2/tests/agent/test_replay.py` from `task2/`; no `playwright` import needed inside `test_replay.py` or `replay.py`.
