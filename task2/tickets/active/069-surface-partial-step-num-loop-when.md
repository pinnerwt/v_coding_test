---
id: 69
slug: surface-partial-step-num-loop-when
status: active
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
filed_pr: null
merged_pr: null
archived_at: null
trigger: 'deferred from PR #101 / ticket #66 per design.md Decision 4 — user-visible
  regression in scoreboard signal.'
---

69. **Surface partial `step_num` from `loop()` when `LLMError` (or any internal exception) escapes.** Per Decision 4 in `openspec/changes/fix-qwen-http-400/design.md` (PR #101), `_run_case`'s exception handler hard-codes `steps=0` because the step count from inside `loop()` is not accessible to the caller when `loop()` raises. As a result, `webvoyager-1` historically reported "step 0" failures even though the actual exhaustion happened at step ~19, hiding the real failure surface in `results.json`. Concrete fix: change `loop()` to either (a) catch its own internal exceptions, attach `step_num` to the `LLMError` (e.g. set a new `LLMError.step_num` attribute) before re-raising, or (b) define a small `LoopFailure(LLMError)` wrapper carrying `step_num` and re-raise that, or (c) make `loop()` return a `RunResult` with `status="failed"` and partial token/step state instead of raising. Update `_run_case`'s `except Exception as exc:` handler to read the partial step count and emit it as `CaseResult.steps`. Tests: a unit test in `tests/test_eval.py` mocks `agent.loop.loop` to raise an `LLMError` after N=12 simulated step iterations and asserts the resulting `CaseResult.steps == 12` (not 0). A second test asserts the existing `test_run_case_failure_detail_includes_llm_error_body` still passes — i.e. `failure_detail` enrichment is not regressed. *Why useful:* unblocks honest WebVoyager scoreboard reporting (a "step 0" failure is qualitatively different from a "step 19" failure for triage). *Trigger:* deferred from PR #101 / ticket #66 per design.md Decision 4 — user-visible regression in scoreboard signal.
