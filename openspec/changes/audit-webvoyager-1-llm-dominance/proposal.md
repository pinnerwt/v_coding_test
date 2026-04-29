## Why

webvoyager-1 exits `reason="seconds_budget"` at step 13 (127s wall-clock) rather than succeeding; the per-step `latency_breakdown_ms` data now available in the run JSON shows LLM time (~6.5s/step × 13 steps ≈ 84s) dominates, but the ranking of three candidate levers — prompt-trim, observation-trim, and path-shorten — has not been quantified, leaving the next tier-5 ticket selection as a coin-flip.

## What Changes

- Add a pytest test `test_step_breakdown_per_step_llm_dominance_in_run_json` that reads the existing webvoyager-1 run JSON artifact and asserts `llm_ms / dispatch_ms > 5` on the median step; the test docstring encodes the quantified lever ranking and names the winner.
- Create a follow-up tier-5 ticket file for the winning lever (prompt-trim), derived from the diagnostic conclusions embedded in the test.

## Capabilities

### New Capabilities
- `benchmark-analysis`: A thin analysis capability covering pytest tests that read existing benchmark run-JSON artifacts, assert structural invariants about per-step latency dominance, and document lever-ranking findings in test docstrings. No production runtime code; purely a diagnostic/audit surface.

### Modified Capabilities
- (none — no existing spec-level behavior changes)

## Impact

- `task2/tests/test_benchmark_analysis.py` — new test file (read-only against the existing artifact; no browser/LLM required).
- `task2/tickets/active/<id>-prompt-trim-webvoyager-1.md` — new follow-up tier-5 ticket for the winning lever.
- No changes to production `agent/`, `scripts/`, or `eval/` code.
- No existing specs modified.
