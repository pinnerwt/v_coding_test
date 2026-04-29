---
id: 88
slug: cache-preserving-compaction-tail-keep
status: active
tier: 5
urgency: P0
axes:
  pass_rate: 30
  tokens_pct: -40
  latency_pct: -50
dependencies: []
pre_flight_gates: []
evidence:
- task2/benchmark/task2-fix-goto-domcontentloaded/webvoyager/20260429_122531.json
- task2/benchmark/task2-implement-fast-path-ticket-archival/webvoyager/20260429_104152.json
related: []
filed_pr: null
merged_pr: null
archived_at: null
trigger: 2026-04-29 — user-driven webvoyager timeout investigation; ticket queue restart
---

88. **Cache-preserving compaction: drop oldest tool/state messages instead of mid-conversation `<elided>` substitution.** Two consecutive WebVoyager runs (`task2-fix-goto-domcontentloaded/webvoyager/20260429_122531.json` and `task2-implement-fast-path-ticket-archival/webvoyager/20260429_104152.json`) show the same per-step latency cliff on `webvoyager-1`: steps 1-12 run at ~5-12s/step, steps 13-20 jump to ~28-31s/step (4× slowdown), and the case ends in `status=timeout` at the 20-step ceiling having burned 322-373s of wall-clock and ~340k prompt tokens. The cliff aligns with `_compact_messages` (`agent/loop.py:174`, default `LLM_CONTEXT_CHAR_BUDGET=80_000`) firing for the first time around step 12-13 — observable as `prompt_tokens` plateauing at ~22-23k after monotonically growing to 23k. Today's compactor *rewrites* mid-conversation message content in place (`_ELIDED_STATE_CONTENT`, `_ELIDED_TOOL_CONTENT`), which mutates the prefix the LLM server has already KV-cached. On the local Qwen 27B endpoint this forces a full 22k-token re-prefill on every subsequent step — exactly the ~22s overhead we observe. **Fix:** rewrite `_compact_messages` to *drop* the oldest non-system messages (preferring whole tool / state / assistant tuples) until the message list fits the budget, leaving the kept tail's contents byte-identical to the prior step's prefix. The LLM server's prefix cache then survives across steps because the only mutation is appending new messages at the end. Tests: (1) unit test in `tests/agent/test_loop.py` constructs a message list that exceeds `budget_chars`, calls `_compact_messages`, and asserts the *kept* messages have content byte-identical to the input (no `<elided>` strings) and that the dropped subset is a contiguous prefix after the system message; (2) regression test asserts that compacting twice in a row with one new state appended each time yields a result whose first N messages are byte-identical to the prior compaction (prefix stability invariant); (3) integration test (skip without live Qwen) runs `webvoyager-1` and asserts no step in `latency_ms_per_step` exceeds 2× the median of steps 1-5 (current baseline cliff ratio is ~4×). *Why useful:* this single change should eliminate the timeout on `webvoyager-1`, cut its prompt-token spend by ~40% (no more re-sending the elided shell of every old state), and bring p95 step latency back into the 5-12s band. **Estimated impact justifies axes pass_rate +30 / tokens -40 / latency -50.** *Trigger:* 2026-04-29 user-driven webvoyager timeout investigation — see ticket queue restart commit.
