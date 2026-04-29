---
id: 73
slug: no-tool-call-planner-stall-early
status: active
tier: 1
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence:
- task2/benchmark/task2-implement-loop-stuck-repeat/webvoyager/20260429_004208.json
related:
- 104
- 70
filed_pr: 106
merged_pr: null
archived_at: null
trigger: 'surfaced by `/done_pr` step 1b on 2026-04-29 after `task2-implement-loop-stuck-repeat`
  WebVoyager run showed webvoyager-1 still timing out at 20 steps despite #70 shipping.
  Cross-run check: same case timed out at 20 steps in `task2-fix-qwen-http-400/webvoyager/20260428_233500.json`
  with the same zero-tool-call shape, so this is a recurring failure pattern, not
  a flake.'
---

73. **No-tool-call planner-stall early-termination in `agent.loop`.** PR #104 / ticket #70 shipped `_stuck_buf` for K=3 byte-identical `(tool_name, args)` tool-call termination, but `webvoyager-1` (Wikipedia "List the latest version of Python") in `task2/benchmark/task2-implement-loop-stuck-repeat/webvoyager/20260429_004208.json` still timed out at `steps=20, $0.2978, 281.6s` — every step's `step_breakdown[i].tools` is `None`, meaning the LLM emitted text-only responses (no tool calls) for the entire run. K=3 stuck-detection cannot fire when the buffer never accumulates entries. Concrete fix: in `agent/loop.py`, alongside `_stuck_buf`, maintain a counter `_consecutive_no_tool_call_steps` that increments by 1 each time a non-final LLM response yields `len(response.tool_calls) == 0` (or `None`) and resets to 0 on any step that produces a tool call. When the counter reaches a small constant (e.g. `_NO_TOOL_CALL_K = 3`), call `_record_step(...)` and return `RunResult(status="failed", reason="no_tool_call_repeat", result=None, evidence=None, verifier=None, steps=step_num, ...)` with the same metric-field discipline as the `stuck_repeat` exit. Add `RunResultReason = Literal["stuck_repeat", "no_tool_call_repeat"]` (extend the existing alias added in PR #104). The plan-step at step 0 (where `tools=None` legitimately by design) MUST NOT count toward the K threshold — gate the counter on `step_num > 0` or on the dispatch path entered. Tests: a stub `LLMClient` that returns `ChatResponse(content="...", tool_calls=[])` for K=3 consecutive calls asserts `loop()` exits with `status="failed"`, `reason="no_tool_call_repeat"`, and `steps == 3`; a control test where the planner emits a `goto` tool call between two no-tool-call steps asserts the counter resets and `loop()` runs to `max_steps` timeout. *Why useful:* `webvoyager-1` has been our worst single-case cost sink for two consecutive runs (this run's $0.30 + 282s mirrors the prior run); it survived #70 because the LLM never even called a tool to be tracked. With this fix paired with #70, both pathological "stuck planner" shapes are bounded and the ~$0.05/case cost ceiling promised in #70's *Why useful* finally applies to webvoyager-1. *Trigger:* surfaced by `/done_pr` step 1b on 2026-04-29 after `task2-implement-loop-stuck-repeat` WebVoyager run showed webvoyager-1 still timing out at 20 steps despite #70 shipping. Cross-run check: same case timed out at 20 steps in `task2-fix-qwen-http-400/webvoyager/20260428_233500.json` with the same zero-tool-call shape, so this is a recurring failure pattern, not a flake.
