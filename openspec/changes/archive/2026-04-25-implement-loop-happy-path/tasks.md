## 1. Failing test (red) — fixture + test scaffold

- [x] 1.1 Create `task2/tests/fixtures/loop_happy_path.html` — a minimal static HTML page containing a visible heading (e.g. `<h1>Hello, loop</h1>`) and a paragraph. This is the 2-step fixture the happy-path test drives against.
- [x] 1.2 Create `task2/tests/agent/test_loop.py`. Add the import `from agent.loop import loop, RunResult`. The import will fail (ImportError) until the module exists — that is the first red bar.
- [x] 1.3 Write `test_run_result_is_frozen` — construct `RunResult(status="succeeded", result={"x": 1}, evidence={"url": "http://a", "text_snippet": "a"})`; attempt to assign to a field; assert `dataclasses.FrozenInstanceError` is raised.
- [x] 1.4 Write `test_loop_happy_path` — the acceptance test. Uses `fixture_server` and `playwright_chromium` fixtures from `conftest.py`. Constructs a fake `llm_client` whose `chat()` method returns a pre-canned sequence: call 1 → `goto(url=<fixture_url>/loop_happy_path.html)`, call 2 → `done(result={"heading": "Hello, loop"}, evidence={"url": <fixture_url>/loop_happy_path.html, "text_snippet": "Hello, loop"})`. Calls `loop("read the heading", browser, fake_llm_client)`. Asserts `result.status == "succeeded"`, `result.evidence["url"]` is non-empty, `result.evidence["text_snippet"]` is non-empty, and `result.result == {"heading": "Hello, loop"}`.
- [x] 1.5 Write `test_loop_timeout` — constructs a fake `llm_client` that never emits `done` or `fail` (returns a no-op tool call or empty content forever). Calls `loop("task", browser, fake_llm_client, max_steps=2)`. Asserts `result.status == "timeout"`.
- [x] 1.6 Write `test_loop_fail` — constructs a fake `llm_client` that emits `fail(reason="blocked")`. Asserts `result.status == "failed"` and `result.result is None`.
- [x] 1.7 From `task2/`, run `uv run pytest tests/agent/test_loop.py -x` and confirm all tests fail with `ImportError: No module named 'agent.loop'`.

## 2. Implementation (green) — `loop.py` module

- [x] 2.1 Create `task2/agent/loop.py`. Add module-level imports: `from __future__ import annotations`, `import json`, `from dataclasses import dataclass`, `from typing import Any`. Do NOT import `agent.supervisor` (self-correction is ticket #10).
- [x] 2.2 Define the `RunResult` frozen dataclass with fields `status: str`, `result: Any`, `evidence: dict | None`.
- [x] 2.3 Define the `TOOLS` module-level constant — a list of four OpenAI-tool-schema dicts: `goto`, `read`, `done`, `fail`. Follow the exact schemas from `design.md`. Do NOT include `click`, `type`, `select`, `wait_for`, `back`, or `screenshot`.
- [x] 2.4 Define the `_build_system_prompt(task: str) -> str` helper — returns a concise system prompt instructing the LLM: you are a browser agent, your task is `{task}`, use the tools provided, call `done` when the task is complete with structured evidence.
- [x] 2.5 Define the `_observe(browser) -> dict` helper — returns `{"url": page.url, "text": page.evaluate("() => document.body.innerText")[:2000]}` using `browser._page`. Returns `{"url": "", "text": ""}` if `_page` is `None`.
- [x] 2.6 Define the `_dispatch(tool_name: str, args: dict, browser) -> str` helper — executes a non-terminal tool call and returns a string result to feed back to the LLM as the tool result message:
  - `goto`: calls `browser.goto(args["url"])`; returns `f"Navigated to {args['url']}"`.
  - `read`: if `args.get("intent")`, calls `locate(browser._page, args["intent"])` to get a `LocateResult`, then calls `browser.read(result.selector)` and returns the text. If no `intent`, calls `browser._page.evaluate("() => document.body.innerText")[:2000]` and returns it.
  - Any unrecognised tool: returns `f"Unknown tool: {tool_name}"`.
- [x] 2.7 Define the `loop(task: str, browser, llm_client, *, max_steps: int = 20) -> RunResult` function:
  - Build initial `messages`: `[{"role": "system", "content": _build_system_prompt(task)}]`.
  - Loop up to `max_steps` times:
    1. Append an observation message: `{"role": "user", "content": f"Current state: {json.dumps(_observe(browser))}"}`.
    2. Call `llm_client.chat(messages, tools=TOOLS)`.
    3. Append the assistant message to `messages` (reconstruct from `ChatResponse`).
    4. If `response.tool_calls` is empty (model returned text, not a tool call): append assistant content as a message and continue (do not crash).
    5. For each `tool_call` in `response.tool_calls`:
       - Parse `json.loads(tool_call.arguments)` to get `args`.
       - If `tool_call.name == "done"`: return `RunResult(status="succeeded", result=args.get("result"), evidence=args.get("evidence"))`.
       - If `tool_call.name == "fail"`: return `RunResult(status="failed", result=None, evidence=None)`.
       - Otherwise: call `_dispatch(tool_call.name, args, browser)` and append a tool-result message `{"role": "tool", "tool_call_id": tool_call.id, "content": <result>}`.
  - After the loop exits without a terminal call: return `RunResult(status="timeout", result=None, evidence=None)`.
- [x] 2.8 From `task2/`, run `uv run pytest tests/agent/test_loop.py::test_run_result_is_frozen -xvs` and confirm it passes.
- [x] 2.9 From `task2/`, run `uv run pytest tests/agent/test_loop.py::test_loop_happy_path -xvs` and confirm it passes.
- [x] 2.10 From `task2/`, run `uv run pytest tests/agent/test_loop.py -xvs` and confirm all tests pass.

## 3. Full suite validation (green bar)

- [x] 3.1 From `task2/`, run `uv run pytest` (full suite) and confirm all existing tests remain green (tickets #1–#8 unaffected).

## 4. Refactor + housekeeping

- [x] 4.1 Reread `task2/agent/loop.py`. Verify: no hardcoded LLM base URL or model; `TOOLS` is a clean module-level constant; type hints present on all public symbols; no dead code.
- [x] 4.2 Confirm `agent/llm.py`, `agent/browser.py`, `agent/locate.py`, `agent/locator_cache.py`, `agent/supervisor.py` are UNCHANGED.
- [x] 4.3 Confirm `task2/pyproject.toml` has no new dependencies (the loop uses only existing modules + stdlib).

## 5. Pre-commit gate

- [x] 5.1 From `task2/`, run `uv run ruff format .` — confirm no files are reformatted.
- [x] 5.2 From `task2/`, run `uv run ruff check .` — confirm zero lint errors.
- [x] 5.3 From `task2/`, run `uv run pytest` — confirm full suite passes.
- [x] 5.4 Commit with conventional message: `feat(task2): add loop.py with 2-step happy-path observe→decide→act cycle`.
