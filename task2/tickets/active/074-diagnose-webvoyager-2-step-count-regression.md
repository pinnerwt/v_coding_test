---
id: 74
slug: diagnose-webvoyager-2-step-count-regression
status: active
tier: 1
urgency: P2
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence:
- task2/benchmark/task2-implement-no-tool-call-repeat/webvoyager/20260429_013158.json
related:
- 106
- 70
- 72
- 66
- 73
- 55
filed_pr: null
merged_pr: null
archived_at: null
trigger: '`/done_pr` step 1b'' aggregate regression check on 2026-04-29 against PR
  #106 (`task2/implement-no-tool-call-repeat`) flagged cost/tokens/latency at +43.6%/+43.6%/+43.5%
  vs prior baseline, all driven by webvoyager-2''s step-count growth.'
---

74. **Diagnose webvoyager-2 step-count regression after PR #106 (8 → 17 steps, $0.10 → $0.27).** PR #106's WebVoyager run at `task2/benchmark/task2-implement-no-tool-call-repeat/webvoyager/20260429_013158.json` shows `webvoyager-2` (arXiv `Diffusion-DPO ICLR 2024`) flipped `succeeded steps=8 $0.0957 lat=100s` (baseline `task2-implement-loop-stuck-repeat`) → `succeeded steps=17 $0.2710 lat=345s`. Status unchanged, but the per-case trace went from `goto/type/click/goto/read/goto/read/done` (8 steps) to `goto/type/click × 9/goto/read/goto/read/done` (17 steps) — the agent emitted **9 consecutive `click` tool calls in steps 3-11** before recovering. This single case drove the suite-level aggregate regression of cost +43.6%, tokens +43.6%, latency +43.5% that tripped `/done_pr` step 1b' on 2026-04-29. Two distinct hypotheses, only the first is testable from the JSON alone: (a) the 9 `click`s carry varying `args` (different result links / menu items on the arXiv search page), so #70's `(tool_name, json.dumps(args))` byte-identical buffer correctly does NOT fire — only the unshipped #72 (`stuck_no_observation_change` digest companion) would catch this; or (b) the 9 `click`s carry identical `args` but #70's reset path on `SupervisorEvent` is firing more often than expected, clearing the buffer between consecutive identicals. The `step_breakdown[].tool_calls` field stores only the tool name, not the args, so resolving (a) vs (b) requires re-running the case with trace events captured to JSONL (`TRACE_PATH=/tmp/wv2.jsonl uv run python -m scripts.bench --suite webvoyager --live --case-id webvoyager-2`) and inspecting `ToolCallEvent.arguments` for steps 3-11. Concrete steps: (1) add a `--case-id <id>` filter to `scripts/bench.py` if absent (deferred from #66); (2) re-run webvoyager-2 with trace capture against the same Qwen endpoint; (3) classify the 9 clicks as identical-args (→ confirm #70 reset bug, file fix) or varying-args (→ confirm #72 is the right detector and accept the regression as environmental until #72 lands); (4) cross-check whether Wikipedia-to-arXiv navigation patterns changed between the two runs (Qwen sampling variance vs DOM change). Tests: a unit test in `tests/agent/test_loop.py` that constructs a stub `LLMClient` emitting 9 `click` calls with byte-identical args between two `goto` calls asserts `_stuck_buf` reaches size 3 within those 9 calls and `loop()` exits with `reason="stuck_repeat"` at step 5 (not step 11) — i.e. a TDD guard that #70 fires on this trace shape if (b) holds. *Why useful:* the trace shape is the most cost-expensive failure mode after #73 — webvoyager-2 alone added $0.18 + 245s + 172K tokens to this run vs baseline. If hypothesis (a) holds, #72 inherits this case as evidence; if (b) holds, #70 has a reset bug worth fixing. Either way, the diagnosis closes a triage gap in the regression-onset workflow that #55 sketches at the suite level. *Trigger:* `/done_pr` step 1b' aggregate regression check on 2026-04-29 against PR #106 (`task2/implement-no-tool-call-repeat`) flagged cost/tokens/latency at +43.6%/+43.6%/+43.5% vs prior baseline, all driven by webvoyager-2's step-count growth.
