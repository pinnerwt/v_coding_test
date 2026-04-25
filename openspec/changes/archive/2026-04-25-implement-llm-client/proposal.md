## Why

Task 2 (the browser automation agent) needs an LLM client as its first building block — every subsequent ticket (planner, locator rerank, supervisor, vision fallback) calls it. CLAUDE.md forbids hardcoding a hosted provider: the deployed Zeabur instance points at a local Qwen3.5 27B at `http://localhost:8090`, but the same code must reach a different OpenAI-compatible endpoint when configured. Ticket #1 of `task2/plan.md` demands this be done TDD-first with mocked HTTP asserting the request shape.

## What Changes

- Add `agent/llm.py`: an OpenAI-compatible chat-completions client.
- Read configuration from environment: `LLM_BASE_URL` (default `http://localhost:8090`), `LLM_MODEL` (required), `LLM_API_KEY` (optional — sent as `Authorization: Bearer …` only when set).
- Expose a `chat(messages, *, model=None, temperature=0, tools=None, seed=None, …)` entry point that returns the parsed response (content, tool_calls, finish_reason, usage).
- POST to `<base_url>/v1/chat/completions` with the OpenAI request body shape.
- Surface HTTP/transport failures as a typed `LLMError` so callers (loop, supervisor) can classify.
- Add tests under `tests/agent/test_llm.py` that mock the HTTP layer (not the contract) and assert: URL composition, headers, body fields, env-var honoring, and error propagation.
- Add `agent/__init__.py` + minimal `pyproject.toml`/`requirements.txt` entries needed to import + run the test (httpx + pytest). No other agent modules introduced here.

## Capabilities

### New Capabilities
- `llm-client`: Configurable OpenAI-compatible chat-completions client used by every Task 2 component that calls an LLM. Owns env-var resolution, request shaping, response parsing, and error typing.

### Modified Capabilities

(none — no existing specs)

## Impact

- New module: `agent/llm.py`, `agent/__init__.py`.
- New tests: `tests/agent/test_llm.py`, plus `tests/__init__.py` if needed.
- New runtime dep: `httpx` (sync client; async can come later when `loop.py` needs it). New dev dep: `pytest`, `pytest-mock` or `respx` for mocking.
- Environment contract introduced: `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`. Documented in this change's design and surfaced in the eventual Task 2 README.
- No deployment impact yet — Zeabur image work happens in ticket #18.
- Downstream tickets (#5 locate L3, #6 locate L4 vision, #8 supervisor, #9 loop, #11 silent-failure guard) will import this client.
