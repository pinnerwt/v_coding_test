## Why

On 2026-04-28, `webvoyager-1` ("List the latest version of Python" / Turing Award on Wikipedia) failed every WebVoyager Tier-0 run with `failure_class="tool_error"` and `failure_detail="LLMError('http 400')"`. The eval runner's exception handler was masking the real failure: it hard-codes `steps=0` and uses `repr(exc)` for `failure_detail`, discarding the rich diagnostic fields (`exc.status`, `exc.body`) already captured by `LLMClient`. Live reproduction on 2026-04-28 captured the verbatim 400 body:

`{"error":{"code":400,"message":"request (34074 tokens) exceeds the available context size (32768 tokens)","type":"exceed_context_size_error","n_prompt_tokens":34074,"n_ctx":32768}}`

The failure occurs at step ≈ 19 (not step 0 as the masked output suggested). By that step the accumulated `messages` list contains ~56 messages: system + alternating user/assistant/tool entries, each `user` message embedding ~6 KB of AX-tree JSON, each `tool` result adding ~2 KB. Cumulative prompt grows from ~1 K tokens at step 1 to ~34 K tokens at step 19, exceeding Qwen's 32 K context window.

Cases 2 (arXiv) and 3 (GitHub) avoid the 400 because their AX trees are smaller and the agent terminates in fewer steps before the window fills.

## What Changes

Two coupled fixes:

**Fix A — diagnostic surfacing** (`scripts/eval.py`): When `_run_case`'s `except Exception` catches an `LLMError`, format `failure_detail` to include `status` and a body snippet instead of opaque `repr(exc)`. Also surface the actual step count reached rather than hard-coding `steps=0`.

**Fix B — context-window compaction** (`agent/loop.py`): Before every `llm_client.chat(messages, tools=TOOLS)` call, apply a sliding-window compaction that keeps total message character length under a configurable budget (default `LLM_CONTEXT_CHAR_BUDGET` env var, fallback `_DEFAULT_CONTEXT_CHAR_BUDGET = 80_000`). Stale `user`-role messages whose content starts with `"Current state: "` are replaced with the literal placeholder `"Current state: <elided>"`. Stale `tool`-role message content is replaced with `"<read tool result elided>"`. The system prompt at `messages[0]` and the most recent complete turn (user + assistant + tool) are always kept verbatim.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `agent-loop`: Add a new requirement for context-window compaction via `_compact_messages`. No existing requirement covers this behavior.
- `eval-runner`: Add a new requirement for structured `failure_detail` when `_run_case` catches an `LLMError`. The current `_classify_failure` requirement in `failure-classification` governs the trace-derived path; the `except` branch in `_run_case` is owned by `eval-runner` (the spec's text confirms `_run_case` sets `failure_class="tool_error"` directly on the exception path).

## Impact

- `task2/agent/loop.py` — add `_compact_messages(messages, budget_chars)` helper; call it before `llm_client.chat(messages, tools=TOOLS)`.
- `task2/scripts/eval.py` — update the `except Exception` handler in `_run_case` to produce richer `failure_detail` for `LLMError` and to surface `step_num` instead of `0`.
- `task2/tests/test_eval.py` — new test `test_run_case_failure_detail_includes_llm_error_body`.
- `task2/tests/agent/test_loop.py` — two new tests: `test_loop_compacts_message_history_under_token_budget` and `test_loop_preserves_most_recent_observation_after_compaction`.
- `task2/tests/scripts/test_bench_qwen_400_regression.py` (new file) — end-to-end regression confirming no `LLMError` after 25+ scripted steps.
- No new dependencies; no API surface changes.
