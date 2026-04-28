## Context

Live reproduction on 2026-04-28 (`webvoyager-1` / Wikipedia Turing Award) confirmed the 400 body:

`{"error":{"code":400,"message":"request (34074 tokens) exceeds the available context size (32768 tokens), try increasing it","type":"exceed_context_size_error","n_prompt_tokens":34074,"n_ctx":32768}}`

Per-step prompt growth: step 1 ≈ 1 K tokens → step 10 ≈ 17 K → step 15 ≈ 27 K → step 19 ≈ 34 K (rejected). The `messages` list in `agent/loop.py` grows unboundedly: `messages[0]` is the system prompt, then each step appends a user message (~6 KB AX-tree JSON), an assistant message, and one or more tool messages (~2 KB each for `read` results). By step 19, 56 messages totaling ~34 K tokens exceed Qwen's 32 K context.

The eval runner's exception handler (lines 256–267 of `scripts/eval.py`) hard-codes `steps=0` and `failure_detail=repr(exc)`, discarding the structured `exc.status` and `exc.body` already stored by `LLMError`. This masks both the true step count and the actual 400 error body in every bench result JSON.

## Goals / Non-Goals

**Goals:**
- Fix A: When `_run_case` catches an `LLMError`, emit a `failure_detail` that includes `status` and a body snippet, and emit the actual `step_num` reached.
- Fix B: Add `_compact_messages(messages, budget_chars)` to `agent/loop.py` and call it before each `llm_client.chat` so the prompt never exceeds the configured character budget.
- TDD: both fixes start with a failing test.

**Non-Goals:**
- Raising the Qwen context window (not in our control).
- Adding retry logic on 400 (context overflow is not a transient error).
- Changing `observe.py` AX-tree limits (separate concern; current `MAX_NODES=200` already caps per-step size; the problem is cumulative across steps).
- Modifying `_classify_failure` (the trace-derived path; `_run_case`'s `except` branch sets `failure_class` directly and is out of scope for `_classify_failure`).

## Decisions

**Decision 1 — character-budget rather than token-budget.**
Token counting requires either a tiktoken-style library (not in our deps) or an LLM round-trip. Character count is a deterministic O(1) proxy: 4 chars ≈ 1 token for typical ASCII JSON, so `80_000` chars ≈ 20 K tokens, leaving a comfortable 12 K token headroom under Qwen's 32 K limit. The budget is configurable via `LLM_CONTEXT_CHAR_BUDGET` so deployers can tune it for endpoints with different windows.

**Decision 2 — elide stale turns, not truncate latest.**
The most recent observation is always needed (it is what the next decision acts on). Eliding old `Current state:` user messages and old `read` tool results degrades gracefully: the model loses historical context but retains the system prompt, recent decisions, and the freshest observation. Older assistant messages (non-tool-call content) and tool-call records are kept verbatim to preserve reasoning continuity; only the large blob text from old user-observation and tool-result messages is replaced.

**Decision 3 — "keep last K turns verbatim" defined as: the system prompt (index 0) + all messages from the most recent user-observation onwards are never elided.**
A "turn" is: one user message + the assistant response to it + any tool messages that follow. The compaction loop walks backwards from the end of `messages` to identify the start of the most recent turn and never elides anything at or after that boundary.

**Decision 4 — Fix A uses `step_num` from the surrounding scope.**
`step_num` is incremented at the top of each loop iteration before the `llm_client.chat` call that can raise. When the exception escapes `loop()`, `step_num` correctly reflects the step that was in progress. The exception handler in `_run_case` currently does not have access to `step_num` because `loop()` raises before returning `RunResult`. Fix A therefore passes `step_num` to `CaseResult.steps` by catching the exception inside `loop()` — no: instead, `_run_case` cannot get `step_num` from outside `loop()`. The correct approach is: `loop()` catches `LLMError` internally, stores partial progress in a new field of `RunResult` (or re-raises with the step count attached), OR `_run_case` uses `0` for steps but enriches `failure_detail` with the body. Per the ticket guidance, surfacing partial step count is "or equivalently" to dropping the hard-code. The minimal approach: `_run_case` enriches `failure_detail` when `isinstance(exc, LLMError)` — the step count from `loop()` is unavailable to the caller, so `steps` remains `0` in the exception path. This is consistent with the ticket's "or, equivalently, drop the hardcoded steps=0" note — the primary goal is `failure_detail` enrichment; step count improvement is secondary and deferred to when `loop()` returns partial state.

**Decision 5 — new test file `tests/scripts/test_bench_qwen_400_regression.py`.**
The regression test exercises `_run_case` end-to-end with a stub `LLMClient` that always returns `goto` tool calls. After 25 steps the test asserts (a) no `LLMError` escapes and (b) the stub's recorded `messages` argument on the last call stays under the character budget. This file lives under `tests/scripts/` to mirror the `scripts/` production path.

## Risks / Trade-offs

[Risk: eliding old observations breaks reasoning continuity on long multi-page tasks] → Mitigated: the most recent observation is always kept; older pages the agent already navigated away from are unlikely to be needed verbatim.

[Risk: `80_000` char budget is wrong for a different model] → Mitigated: `LLM_CONTEXT_CHAR_BUDGET` env var allows per-deployment override; default is conservative (≈ 20 K token equivalent) vs. Qwen's 32 K.

[Risk: compaction interacts with multi-tool-call steps (multiple `tool` messages in one turn)] → The compaction function identifies turn boundaries by `role == "user"` messages with `"Current state: "` prefix, not by tool messages, so partial multi-tool turns are not split.

## Open Questions

None. Root cause is fully characterized from the live capture; both fix strategies are specified in the ticket.
