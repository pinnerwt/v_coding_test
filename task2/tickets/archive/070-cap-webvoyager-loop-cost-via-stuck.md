---
id: 70
slug: cap-webvoyager-loop-cost-via-stuck
status: archived
tier: 2
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related:
- 101
- 66
- 69
filed_pr: null
merged_pr: null
archived_at: '2026-04-28'
trigger: 'user-flagged 2026-04-28 ("are we performing worse than before?") after PR
  #101''s WebVoyager run showed cost/latency/tokens regressing 160-170% vs baseline
  despite the http 400 fix being correct.'
---

70. **Cap WebVoyager loop cost via stuck-state early-termination in `agent.loop`.** After PR #101 / ticket #66 shipped `_compact_messages`, `webvoyager-1` (Wikipedia "List the latest version of Python") flipped from `failed (steps=0, $0.0000)` to `timeout (steps=20, $0.3064)`: the compaction fix prevented the http 400 crash, but the planner still cannot converge on the task within `max_steps=20` and the loop now consumes the full step budget without progress. Net regression on benchmark axes vs baseline (`task2-benchmarks-readme-and-tier0/webvoyager/baseline.json`): **cost +160% ($0.1551 → $0.4023), prompt tokens +164% (149,389 → 393,771), p50/p95 latency +170% (145s → 390s) across the 3-case suite**, all driven by this single case. The agent has no early-termination heuristic — it loops to `max_steps` even when stuck. Concrete fix: in `agent/loop.py`, track the last K (e.g. K=3) `(tool_name, tool_args)` tuples emitted by the LLM. When the most recent K are byte-identical, emit `RunResult(status="failed", reason="stuck_repeat")` immediately. Optionally also: when the `axt_digest` (or a cheap hash of the AX-tree JSON) for the last K observations is identical AND the planner has not advanced its `Plan progress` step, treat as stuck. Tests: a unit test where a stub `LLMClient` returns `goto("about:blank")` 5 times in a row asserts `loop()` exits with `status="failed"` and `steps == 3` (the K threshold), not `steps == 20`. A second test asserts a healthy alternation of tool calls runs to natural completion without false-positive stuck detection. *Why useful:* puts a bounded cost ceiling on impossible-to-converge cases; webvoyager-1 burned $0.31 + 360s on this run for zero signal. With early-termination: ~$0.05 max per stuck case. Pair with #69 (partial step_num surfacing) for honest scoreboard reporting on the partial trajectory. *Trigger:* user-flagged 2026-04-28 ("are we performing worse than before?") after PR #101's WebVoyager run showed cost/latency/tokens regressing 160-170% vs baseline despite the http 400 fix being correct.
