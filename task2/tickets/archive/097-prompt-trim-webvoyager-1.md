---
id: 97
slug: prompt-trim-webvoyager-1
status: archived
tier: 5
urgency: P1
axes:
  pass_rate: 30
  tokens_pct: -30
  latency_pct: -25
dependencies: []
pre_flight_gates: []
evidence:
- task2/benchmark/task2-propagate-runresult-reason-to-caseresult/webvoyager/20260429_203237.json
- task2/tests/test_benchmark_analysis.py
related:
- 96
filed_pr: 154
merged_pr: 154
archived_at: "2026-04-29"
trigger: "2026-04-29 — diagnostic from ticket #96 ranked prompt-trim as the highest-ROI lever among (prompt-trim, path-shorten, observation-trim)"
---

**Trim stale prompt context to bring webvoyager-1 within the 120s budget.**

Ticket #96 diagnostic (`task2/tests/test_benchmark_analysis.py`, see `test_step_breakdown_per_step_llm_dominance_in_run_json` docstring) confirmed that webvoyager-1 exits `reason="seconds_budget"` at step 13 with 127s wall-clock, with LLM time accounting for ~105s of the total. Prompt tokens grow from 1,084 at step 1 to 21,522 at step 13 — a 20x accumulation over 13 steps — and step 13 alone incurs 29.9s of LLM latency on 21,522 prompt tokens. The lever ranking from ticket #96 places prompt-trim as the clear winner: trimming stale tool-result messages and AX-tree noise from the conversation history would cut per-step prompt tokens by approximately 30%, saving ~31s of LLM time (0.30 × 105s) and bringing the 127s wall-clock to ~96s — comfortably under the 120s budget — compared to path-shortening (~20s saved, borderline at ~107s) and observation-trim (~6s saved on step 1 only, leaving ~121s).

## Acceptance

TDD shape:

1. **Unit test on the prompt-builder**: call the trim function directly with an in-memory list of synthetic chat messages (no LLM mock, no network) and assert that tool-result messages older than N steps are dropped from the returned conversation history. The test must fail before the trim is implemented and pass after.

2. **Benchmark assertion**: `webvoyager-1` achieves `status="succeeded"` and `reason is None` within the 120s budget in **at least 2 of 3 consecutive fresh benchmark runs** after the trim is applied. The 2-of-3 qualifier accounts for live-web and LLM nondeterminism (network jitter, sampling variance) and avoids a flaky completion gate; a single passing run is insufficient.

## References

- Diagnostic source: ticket #96 (`task2/tickets/active/096-diagnose-webvoyager-1-llm-time-dominance.md` until merged, then `task2/tickets/archive/...`)
- Lever ranking docstring: `task2/tests/test_benchmark_analysis.py::test_step_breakdown_per_step_llm_dominance_in_run_json`
- Evidence artifact: `task2/benchmark/task2-propagate-runresult-reason-to-caseresult/webvoyager/20260429_203237.json`
