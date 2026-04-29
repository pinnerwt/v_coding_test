---
id: 67
slug: auto-tune-compact-messages-budget-qwen
status: archived
tier: 5
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related:
- 66
filed_pr: null
merged_pr: null
archived_at: '2026-04-29'
trigger: 'deferred from PR #101 (ticket #66) on 2026-04-28 to keep the fix-PR scope
  tight; user surfaced the `/props` endpoint mid-iteration as the authoritative source
  for runtime context size.'
---

67. **Auto-tune `_compact_messages` budget from Qwen `/props.default_generation_settings.n_ctx`.** Ticket #66 shipped `_compact_messages(messages, budget_chars)` in `agent/loop.py` with a static `_DEFAULT_CONTEXT_CHAR_BUDGET = 80_000` (≈ 20K tokens at 4 chars/token, comfortable headroom under Qwen's 32K window). The runtime context window is actually exposed by the llama.cpp endpoint at `GET http://localhost:8090/props` under `default_generation_settings.n_ctx` (verified 2026-04-28: returns `32768`, matching the 400 body's `n_ctx` field exactly). This ticket: at `LLMClient` construction (or first chat call), probe `<base_url>/props` once, parse `default_generation_settings.n_ctx`, and derive a character budget = `int(n_ctx * 0.6 * 4)` (60% of the window in tokens × 4 chars/token, leaving 40% headroom for completion + safety). Pass that into `loop()` and onwards into `_compact_messages` instead of reading a static env var, with `LLM_CONTEXT_CHAR_BUDGET` still honored as an explicit override. If `/props` is unreachable or doesn't expose `n_ctx`, fall back to `_DEFAULT_CONTEXT_CHAR_BUDGET`. Tests: stub a `/props` response with `n_ctx=32768` → budget computed to ~78400 chars; stub `/props` returning 404 → falls back to 80_000; `LLM_CONTEXT_CHAR_BUDGET=50000` env override beats the auto-tuned value. *Why useful:* removes the magic number, makes the budget endpoint-aware so the same code is correct for a 32K Qwen and a 128K Llama without per-deployment tuning, and the auto-tune is a one-time HTTP call so the loop hot path is unaffected. *Trigger:* deferred from PR #101 (ticket #66) on 2026-04-28 to keep the fix-PR scope tight; user surfaced the `/props` endpoint mid-iteration as the authoritative source for runtime context size.
