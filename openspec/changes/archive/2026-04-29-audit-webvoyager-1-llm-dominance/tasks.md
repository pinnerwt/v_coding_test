## 1. Red — write the failing test

- [x] 1.1 Confirm the run JSON artifact exists at `task2/benchmark/task2-propagate-runresult-reason-to-caseresult/webvoyager/20260429_203237.json` and inspect `cases[0].step_breakdown` to verify field names (`latency_breakdown_ms`, `llm_ms`, `dispatch_ms`, `prompt_tokens`).
- [x] 1.2 Create `task2/tests/test_benchmark_analysis.py` with function `test_step_breakdown_per_step_llm_dominance_in_run_json`. The docstring SHALL encode: lever (a) prompt-trim saves ~31s (30% × 105s LLM total, winner), lever (b) path-shorten saves ~20s (3 steps × 6.5s), lever (c) observation-trim saves ~6s (step-1 only). The function body asserts: `cases[0]["reason"] == "seconds_budget"`, `len(step_breakdown) == 13`, `llm_ms > 5 * dispatch_ms` for all steps with index >= 1 (multiplicative form, safe when `dispatch_ms == 0`), and `step_breakdown[-1]["prompt_tokens"] >= 10 * step_breakdown[0]["prompt_tokens"]`.
- [x] 1.3 Run `uv run pytest task2/tests/test_benchmark_analysis.py -v` from `task2/` and confirm the test is discovered. If the artifact path is wrong, correct the `pathlib.Path` construction before proceeding.

## 2. Green — confirm test passes

- [x] 2.1 Run `uv run pytest task2/tests/test_benchmark_analysis.py -v` and confirm all assertions pass (the artifact is committed and the data satisfies every invariant).
- [x] 2.2 Run `uv run ruff check task2/tests/test_benchmark_analysis.py` and fix any lint issues.
- [x] 2.3 Run `uv run ruff format task2/tests/test_benchmark_analysis.py` and confirm no diff.

## 3. Follow-up ticket — file the winning lever

- [x] 3.1 Create `task2/tickets/active/097-prompt-trim-webvoyager-1.md` as a tier-5 ticket targeting prompt-trim: trim stale tool-result messages and AX-tree noise from the conversation history to reduce per-step `prompt_tokens` by ~30%, saving ~31s on webvoyager-1 and bringing total wall-clock from 127s to ~96s. The ticket SHOULD reference ticket #96 as its diagnostic source and cite the `test_step_breakdown_per_step_llm_dominance_in_run_json` docstring as evidence.

## 4. Commit

- [x] 4.1 Stage `task2/tests/test_benchmark_analysis.py` and `task2/tickets/active/097-prompt-trim-webvoyager-1.md`. Commit with message `test(task2): diagnose webvoyager-1 LLM dominance; file prompt-trim follow-up (#96)`.
