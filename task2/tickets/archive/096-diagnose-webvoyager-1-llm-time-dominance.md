---
id: 96
slug: diagnose-webvoyager-1-llm-time-dominance
status: archived
tier: 4
urgency: P2
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence:
- task2/benchmark/task2-propagate-runresult-reason-to-caseresult/webvoyager/20260429_203237.json
- task2/agent/loop.py
related:
- 91
- 95
filed_pr: 152
merged_pr: 152
archived_at: "2026-04-29"
trigger: "2026-04-29 — /done_pr post-merge run on PR #149 confirmed webvoyager-1 reason=seconds_budget (127s wall-clock at step 13); per-step breakdown shows LLM dominates (~6.5s/step) and observation_ms is one-time 12.4s on step 1; need to localize whether prompt size, model latency, or step count is the most-tractable lever before filing a tier-5 fix"
---

96. **Diagnose webvoyager-1 LLM-time-per-step dominance and propose smallest lever to bring it under the 120s wall-clock budget.** Now that `RunResult.reason` propagates to the benchmark JSON (PR #149), the diagnosis is unambiguous: webvoyager-1 hits `reason="seconds_budget"` at step 13 (127s wall-clock), not max_steps. Inspecting `task2/benchmark/task2-propagate-runresult-reason-to-caseresult/webvoyager/20260429_203237.json` `step_breakdown[]`, the cost is concentrated on **LLM time**: step 1 spends 12.4s in observation (initial AX-tree build after `goto`) + 3.1s LLM, but steps 2-13 spend ~7ms in observation and ~6.5s in LLM each (e.g. step 2: `llm_ms=6511 observation_ms=70 dispatch_ms=75`). So 13 × ~6.5s LLM ≈ 84s of pure LLM time, plus the 12.4s step-1 observation, plus ~2-5s/step dispatch on click/goto = the 127s budget hit. There is no stuck/no-progress pattern — the agent is making forward progress every step, the per-step cost is just too high. **Goal:** produce a one-page diagnostic write-up (in the ticket body or a follow-up `task2/benchmark/<branch>/notes/<id>.md`) that quantifies the three candidate levers and picks the smallest one to file as a tier-5 ticket: (a) **prompt-trim** — what is the per-step `prompt_tokens` count? Does it grow over the run? Are there stale tool messages or AX-tree noise that could be pruned? Estimate: a 30% prompt cut saves ~30% of LLM time → ~40s saved, fits under 120s. (b) **observation-trim** — step 1's 12.4s `observation_ms` is the largest single cost; is it pure AX-tree build, or does it include playwright `waitForLoadState`? `agent/loop.py` and `agent/observe.py` already have a `domcontentloaded` switch (#85). Estimate: cutting 6s from step 1 observation saves ~5% of total. (c) **path-shorten** — webvoyager-1 takes 13 steps to (almost) succeed at; is there a step-2 prompt heuristic ("you have already navigated; skip planning page load") that would fold steps 2-3 into one? Estimate: -3 steps × ~6.5s = ~20s saved. **Tests:** for the diagnostic itself: `test_step_breakdown_per_step_llm_dominance_in_run_json` reading the run JSON, asserting `step_breakdown[i].latency_breakdown_ms.llm_ms / latency_breakdown_ms.dispatch_ms > 5` on the median step; documents the lever ratios in the docstring. **Done bar:** the ticket body is updated with the answer to "which lever has the largest expected return per implementation effort" and a follow-up tier-5 ticket file is written for that lever. *Why useful:* tier 4 diagnostic — without it, the next iteration's tier-5 ticket-selection on webvoyager-1 is a coin-flip between three plausible levers (a/b/c) with very different fix shapes. Now that #95 surfaces `reason=seconds_budget`, the data is in the artifact; this ticket extracts the actionable insight. *Trigger:* 2026-04-29 — /done_pr post-merge analysis on PR #149 found that with `reason` now in the JSON, the bottleneck is unambiguously LLM-per-step (≥84s of the 127s ceiling), but the lever ranking among (a)/(b)/(c) is still a judgment call requiring per-case prompt-size and step-count inspection.
