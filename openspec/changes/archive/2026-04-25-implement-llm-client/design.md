## Context

`agent/llm.py` is the foundation of every LLM-using component in Task 2: planner, decision loop, locator rerank, vision fallback, supervisor classifier, and evidence verifier. They all need one configurable, OpenAI-compatible chat-completions client.

Constraints from the brief and CLAUDE.md:
- The deployed Zeabur instance points at a local Qwen3.5 27B at `http://localhost:8090` (OpenAI-compatible). Code MUST NOT hardcode a hosted provider.
- TDD is non-negotiable. Mock the network, not the contract — meaning tests assert what we send/receive over HTTP, not what an in-process stub returned.
- Trace replay (plan §"Replay contract") requires deterministic re-runs given `model` + `seed` + `temperature=0`. The client must therefore round-trip these fields to the API and report `usage`/`finish_reason` faithfully.

Current state: empty repo apart from `task2/plan.md` and an `openspec/` scaffold. No `agent/` package, no test harness, no Python runtime files.

## Goals / Non-Goals

**Goals:**
- A small, synchronous `chat()` function that takes OpenAI-style `messages` and optional `tools`, posts to `<LLM_BASE_URL>/v1/chat/completions`, and returns a parsed response object.
- Env-driven configuration with sane defaults (`LLM_BASE_URL=http://localhost:8090`) and explicit override via function args (so tests don't need env mutation).
- Distinguish transport/HTTP errors from API-layer errors via a single `LLMError` exception with structured fields (`status`, `body`, `cause`).
- Tests prove: URL composition, header set, body shape (model, messages, temperature, tools, seed when provided), env-var honoring, auth header presence/absence, and error mapping.

**Non-Goals:**
- Streaming responses (`stream=true`). Plan §traces records full prompts/responses; streaming complicates trace capture and no caller needs it yet.
- Async client. `loop.py` is currently spec'd as sequential observe→act; sync is enough. Adding async later is mechanical with `httpx.AsyncClient`.
- Tool-call execution. The client returns `tool_calls` verbatim; dispatching them is the loop's job.
- Token counting / cost estimation. We surface `usage` from the response; cost math lives in the trace writer (ticket #12).
- Retry / backoff. The supervisor (ticket #8) owns recovery semantics; the client raises and lets the caller decide.
- Provider-specific quirks (OpenAI function-calling pre-1106 format, Anthropic translation, etc.). Qwen exposes the OpenAI 1.x shape — we target that.

## Decisions

### D1: HTTP library — `httpx` over `requests` or `openai`

- `openai` SDK: rejected. It pins to OpenAI's evolving API surface, drags retries/telemetry we don't want, and the brief explicitly forbids hardcoding a hosted provider. Even though it supports `base_url`, using it makes the test "mock the contract" easy to violate.
- `requests`: viable but no async path when `loop.py` eventually wants concurrency, and `respx` (mocking) targets `httpx`.
- `httpx`: sync now, async-ready later, first-class mocking via `respx`. **Chosen.**

### D2: Test mocking — `respx` over `unittest.mock` patching

- `unittest.mock.patch("httpx.Client.post")`: brittle, asserts call args rather than wire format, lets bugs in URL composition slip past.
- `respx`: intercepts at the HTTP transport layer, lets us assert the exact `httpx.Request` (URL, headers, JSON body). This matches the CLAUDE.md rule "mock the network, not the contract." **Chosen.**

### D3: Configuration resolution order

For each parameter (`base_url`, `model`, `api_key`):
1. Explicit kwarg passed to `chat(...)` or to a `LLMClient(...)` constructor.
2. Environment variable (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`).
3. Default (only `base_url` has one: `http://localhost:8090`).

`model` with no kwarg and no env var raises `LLMError("model not configured")` at call time — fail fast, don't silently send `None`.

`api_key` is optional. When unset, the `Authorization` header is omitted entirely (local Qwen doesn't require it). When set, sent as `Authorization: Bearer <key>`.

### D4: Public surface — function + class

```python
# Module-level convenience for one-shot calls (planner, supervisor):
def chat(messages, *, model=None, temperature=0.0, tools=None, seed=None,
         base_url=None, api_key=None, timeout=60.0) -> ChatResponse: ...

# Class for callers that want to reuse a client across many calls (loop.py):
class LLMClient:
    def __init__(self, *, base_url=None, model=None, api_key=None, timeout=60.0): ...
    def chat(self, messages, *, model=None, temperature=0.0, tools=None, seed=None) -> ChatResponse: ...

@dataclass(frozen=True)
class ChatResponse:
    content: str | None
    tool_calls: list[ToolCall]            # empty list, never None
    finish_reason: str
    model: str
    usage: Usage                          # prompt/completion/total tokens
    raw: dict                             # full parsed JSON, for the trace
```

`raw` is kept so `LLMCallEvent.response` (plan §traces) can record exactly what came back without lossy normalization.

### D5: `seed` and `temperature` defaults

- `temperature` defaults to `0.0`. The replay contract assumes deterministic outputs; a hot temperature would break it. Callers (e.g. evidence verifier when sampling alternatives) can override.
- `seed` is `None` by default and only sent when explicitly passed. Not all OpenAI-compatible servers honor it; sending it unconditionally would just bloat the body and pollute traces.

### D6: Error model

Single `LLMError(Exception)` with attributes:
- `kind`: `"config" | "transport" | "http" | "decode"`
- `status`: int | None (HTTP status when applicable)
- `body`: str | None (response body, truncated to 2KB for trace safety)
- `cause`: original exception | None

Why one class: callers (the supervisor) classify by `kind`, not by exception type. Multiple classes would just push isinstance ladders into every caller.

### D7: Tool-call body shape

We pass `tools` through verbatim if the caller supplies it (OpenAI 1106+ shape: `[{"type": "function", "function": {…}}]`). We do NOT invent a schema — the locator-rerank prompt and decision prompt own their tool definitions. The client's contract is "if you give me tools, I'll forward them and parse `tool_calls` out of the response."

## Risks / Trade-offs

- **[Risk]** Qwen 3.5 27B's OpenAI-compat shim may diverge subtly (e.g., not return `tool_calls` reliably, may return them inside `content`). → **Mitigation**: integration smoke test against the local endpoint behind a `--live` flag (separate from this ticket; fits ticket #17). The unit tests here mock the canonical OpenAI shape; we'll add a Qwen-specific compat test the first time we see drift.
- **[Risk]** No retry → transient network blips fail the whole task. → **Mitigation**: by design — supervisor owns recovery. If we discover the supervisor is too coarse, we can add a single retry with jitter behind a kwarg later. Don't pre-build it.
- **[Risk]** Synchronous client caps concurrency to one in-flight LLM call per worker. → **Mitigation**: acceptable for the demo (single browser per request anyway, per plan §Deployment); revisit when concurrency requirements appear.
- **[Trade-off]** `raw` dict in `ChatResponse` keeps the door open to provider-specific fields, at the cost of not enforcing a strict schema on the response. The strict, normalized fields (`content`, `tool_calls`, etc.) are the ones callers should read; `raw` is for the trace.

## Migration Plan

N/A — net-new module. No existing callers, no backwards compatibility surface.

## Open Questions

- None blocking. Streaming and async can be added when a downstream caller needs them.
