## ADDED Requirements

### Requirement: LLM-dominance assertion on webvoyager-1 run JSON

The test module `task2/tests/test_benchmark_analysis.py` SHALL contain a function `test_step_breakdown_per_step_llm_dominance_in_run_json` that reads the committed benchmark run artifact at `task2/benchmark/task2-propagate-runresult-reason-to-caseresult/webvoyager/20260429_203237.json` and asserts the following structural invariants documenting LLM-per-step dominance:

- The first case in the `cases` array SHALL have `reason == "seconds_budget"`.
- The case SHALL have exactly 13 entries in `step_breakdown`.
- For every step with zero-based index >= 1 (step 2 onward, indices 1-12), `latency_breakdown_ms.llm_ms` SHALL be greater than `5 * latency_breakdown_ms.dispatch_ms`. The multiplicative form is required to avoid `ZeroDivisionError` on any future cached step where `dispatch_ms == 0`.
- `step_breakdown[-1]["prompt_tokens"]` (final step) SHALL be at least 10× `step_breakdown[0]["prompt_tokens"]` (step 1), documenting prompt-token accumulation as lever (a).

The test docstring SHALL encode the lever ranking: (a) prompt-trim saves ~28s (30% of ~94s LLM total, largest ROI), (b) path-shorten saves ~20s (remove 3 steps × 6.5s), (c) observation-trim saves ~6s (step-1 only); and SHALL name prompt-trim as the winning lever.

The test SHALL use only the Python standard library (`json`, `pathlib`) — no fixtures, no mocking, no network access.

#### Scenario: Run JSON exists and is parseable

- **WHEN** `test_step_breakdown_per_step_llm_dominance_in_run_json` runs in a clean `uv run pytest` invocation
- **THEN** the test SHALL pass without skips or xfails, confirming the artifact is present and the LLM-dominance ratio holds

#### Scenario: reason field is seconds_budget

- **WHEN** `cases[0]["reason"]` is read from the run JSON
- **THEN** it SHALL equal `"seconds_budget"`

#### Scenario: LLM dominates dispatch on all non-goto-initial steps

- **WHEN** `latency_breakdown_ms` is read for each of steps 2-13 (indices 1-12 in zero-based `step_breakdown`)
- **THEN** `llm_ms` SHALL be greater than `5 * dispatch_ms` for every such step (multiplicative form, safe when `dispatch_ms == 0`)

#### Scenario: Prompt tokens grow at least 10x from step 1 to step 13

- **WHEN** `step_breakdown[0]["prompt_tokens"]` and `step_breakdown[-1]["prompt_tokens"]` are compared
- **THEN** the final step's `prompt_tokens` SHALL be at least 10 times the first step's `prompt_tokens`
