## Context

After tickets #1–#8, `task2/agent/` contains:
- `llm.py` — `LLMClient.chat(messages, *, tools, ...)` → `ChatResponse` with `tool_calls: list[ToolCall]`.
- `browser.py` — `Browser.goto(url)`, `Browser.read(selector)`, `Browser.screenshot()`, `Browser.click_at(x, y)`.
- `locate.py` — `locate(page, intent, *, llm_chat=None, cache=None)` → `LocateResult`; raises `LocatorMiss` on exhaustion.
- `locator_cache.py` — `LocatorCache` (SQLite-backed).
- `supervisor.py` — `Supervisor.handle(miss, *, current_tier)` → `EscalationDecision`.

None of these compose into a running loop yet. `loop.py` is the first module that uses all of them together.

Constraints:
- **TDD non-negotiable.** Tests before code. The acceptance criterion is a 2-step task on a local fixture completing with `status="succeeded"` and non-empty evidence.
- **`LLM_BASE_URL` / `LLM_MODEL` configurable**, never hardcoded to a hosted provider.
- **`uv` + `ruff`** only; lint clean before done.
- **Happy path only.** Self-correction (ticket #10), unverified-evidence guard (ticket #11), and full trace persistence (ticket #12) are explicitly out of scope.
- **Minimal tool surface.** Only the tools the 2-step test exercises must be implemented: `goto`, `read`, `done`. `fail` is included as a clean exit for the LLM; `click` and `type` are deferred to later tickets.

## Goals / Non-Goals

**Goals:**

- A `loop(task, browser, llm_client, *, max_steps=20)` function in `task2/agent/loop.py` that:
  - Builds an observation (URL + page text summary) from the current browser state.
  - Calls the LLM with the task + observation + tool schemas in a loop.
  - Dispatches the LLM's `tool_call` to the appropriate browser action.
  - Exits with `RunResult(status="succeeded", result=..., evidence=...)` when the LLM calls `done(result, evidence)`.
  - Exits with `RunResult(status="timeout", ...)` when `max_steps` is exhausted.
  - Exits with `RunResult(status="failed", ...)` when the LLM calls `fail(reason)`.
- A `RunResult` frozen dataclass with `status`, `result`, `evidence` fields.
- `done`'s evidence argument is a dict with at minimum `url` and `text_snippet`. The loop accepts any non-empty evidence dict for the happy path (the unverified guard is ticket #11).
- A minimal fixture `loop_happy_path.html` and a `test_loop.py` that mocks the LLM and drives a 2-step happy path.

**Non-Goals:**

- Self-correction via supervisor (ticket #10). The loop does not catch `LocatorMiss` in this ticket; if `locate` fails, the exception propagates (and would exit `failed`), but no test exercises that path here.
- Unverified-evidence guard (ticket #11). An empty evidence dict in `done` is not explicitly blocked here.
- Full trace persistence (ticket #12). The loop does not write `LLMCallEvent`, `ObservationEvent`, etc. to SQLite.
- `click`, `type`, `select`, `wait_for`, `back`, `screenshot` tools — added in later tickets as tests demand them.
- USD budget tracking beyond step count. The `max_steps` cap is the only bound for this ticket.
- `observe.py` / `plan.py` modules from the architecture diagram. The loop builds its own minimal observation inline (URL + page text); those modules are ticket #4 and #5 concerns.

## Decisions

### Loop function signature: `loop(task, browser, llm_client, *, max_steps)` not a class

A class `AgentLoop` with an async `run()` method would be more extensible, but the test fixture is synchronous (Playwright sync API), the LLM client is synchronous (`httpx.Client`), and the CLAUDE.md rule is "no abstractions for hypothetical second callers." A top-level function is the minimal shape.

Alternative considered: a class with internal state so multiple methods can share step/budget counters. Deferred to ticket #12 when the trace writer needs access to that state. For this ticket, the function closure carries sufficient state.

### Observation format: URL + page text, not full AX tree

The plan calls for `agent/observe.py` to produce a "compact AX tree" observation. That module is not yet built (ticket #4 is a separate backlog item). For this ticket we emit a minimal observation: `{"url": url, "text": page.evaluate("() => document.body.innerText").strip()[:2000]}`. This is sufficient to unblock the 2-step happy-path test and will be replaced when `observe.py` lands.

Alternative considered: call `Browser.read("body")` for page text. Rejected — `Browser.read` calls `text_content()` which includes hidden text; `innerText` is closer to what the user sees. Using `page.evaluate(...)` directly via the `Browser._page` internal is acceptable here (the loop already owns the browser instance).

### LLM tool schema: `done` and `fail` as terminal tools, `goto` and `read` as action tools

The loop exposes four tools to the LLM:

```python
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "goto",
            "description": "Navigate the browser to a URL.",
            "parameters": {
                "type": "object",
                "properties": {"url": {"type": "string", "description": "Absolute URL to navigate to"}},
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read visible text from the page, optionally targeting an element by intent (e.g. 'the article heading'). Returns the text content.",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {"type": "string", "description": "Optional: describe which element to read (e.g. 'the search result heading'). Omit to read the full page body."}
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Mark the task as complete and return the result with evidence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "result": {"type": "object", "description": "Structured result data from the task"},
                    "evidence": {
                        "type": "object",
                        "description": "Evidence supporting the result. MUST include 'url' (string) and 'text_snippet' (string).",
                        "properties": {
                            "url": {"type": "string"},
                            "text_snippet": {"type": "string"},
                        },
                        "required": ["url", "text_snippet"],
                    },
                },
                "required": ["result", "evidence"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fail",
            "description": "Mark the task as failed with a reason (e.g. login wall, captcha, page not found).",
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
            },
        },
    },
]
```

`click` and `type` are intentionally absent. When the test fixture requires them (ticket #10 or later), they are added at that time.

### `read` dispatch: use `Browser.read(selector)` for intent-scoped reads, `page.evaluate(innerText)` for full-page reads

When the LLM calls `read(intent="...")`, the loop calls `locate(page, intent)` → selector → `browser.read(selector)`. When `intent` is omitted, it reads the full page body via `page.evaluate(...)`. This keeps `locate.py` in the path for element-targeted reads and satisfies the plan's "targets are intents, not selectors" requirement.

Alternative considered: always pass the intent through `locate.py`. Rejected — locate.py's `parse_intent` requires a role token suffix (e.g. "Submit button"); a full-page body read has no element intent. The two modes are genuinely different.

### Test strategy: mock LLM, real browser + local fixture

The test replaces `LLMClient.chat` with a deterministic callable that returns a canned `ChatResponse` sequence. The browser runs real Playwright against a local HTTP fixture (same pattern as `test_supervisor.py`'s integration test and all existing locate/browser tests).

Mocking the network (httpx) rather than the LLM contract is the rule, but here we mock at the `LLMClient` API boundary (passing a fake `llm_client` object) because:
1. The test's goal is to verify the loop's dispatch logic, not the LLM's output quality.
2. The CLAUDE.md rule "mock the network, not the contract" means we do NOT mock `browser.goto` or `browser.read`; the browser must execute real Playwright. Mocking the LLM is acceptable because we are testing the loop composition, not the LLM's tool-calling behavior.

The fixture is a single static HTML page with a known heading; the mock LLM emits: step 1 → `goto(url=fixture_url)`, step 2 → `read(intent=None)` (full body), step 3 → `done(result={"heading": "..."},  evidence={"url": fixture_url, "text_snippet": "Hello"})`.

### `RunResult`: frozen dataclass, not a dict or NamedTuple

Matches the pattern from `EscalationDecision` and `LocateResult`. Keyword-only access, safe against accidental positional misuse, easy to extend with new fields.

### `loop.py` does NOT import `supervisor.py` for this ticket

The happy path by definition has no locator misses. Importing `supervisor.py` and wiring it into the exception path is ticket #10's job. For this ticket, any `LocatorMiss` or other exception propagates unhandled and would surface as an uncaught exception in the test — which is fine because the happy-path fixture is designed so no misses occur.

## Risks / Trade-offs

- **`Browser._page` is accessed directly** for the inline page-text observation. `_page` is a semi-private attribute (single leading underscore). Mitigation: the loop and browser are in the same package; this coupling is documented and will be replaced when `observe.py` lands.

- **Canned LLM mock in tests does not validate the actual system prompt.** A real Qwen call would surface prompt-quality issues. Mitigation: the manual eval flow (running against the live LLM) is the gate for prompt quality; the unit test gate is dispatch correctness. This is consistent with how all prior LLM-touching tests are structured.

- **The 2-step fixture means the loop's observation-build logic is barely exercised.** A multi-step task would stress it more. Mitigation: ticket #10's self-correction test will use a 3+ step scenario through a more adversarial fixture.

- **`max_steps` exhaustion returns `status="timeout"` with no result.** A caller that ignores the status field would silently consume an empty result. Mitigation: the `RunResult` dataclass makes `status` explicit; ticket #14 (API server) will surface it as a 200 with `status: "timeout"` in the JSON body.
