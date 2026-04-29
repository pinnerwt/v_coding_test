---
id: 91
slug: per-step-phase-latency-breakdown
status: active
tier: 2
urgency: P2
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence:
- task2/benchmark/task2-fix-goto-domcontentloaded/webvoyager/20260429_122531.json
- task2/agent/loop.py
related:
- 88
filed_pr: null
merged_pr: null
archived_at: null
trigger: 2026-04-29 — user-driven webvoyager timeout investigation; ticket queue restart
---

91. **Split per-step latency into `observation_ms` / `llm_ms` / `dispatch_ms` in `step_breakdown`.** Today `step_breakdown[].latency_ms` is one number (`agent/loop.py:250`, `step_ms = (time.monotonic() - t0) * 1000`) covering observation building (`build_observation` → AX-tree CDP traversal + `page.title()` + fingerprint hash), the `llm_client.chat` round-trip, and tool dispatch (`_dispatch` — playwright `goto`/`click`/`type`/`read`). When `webvoyager-1` step latency cliffs from ~7 s to ~30 s after step 12 we *infer* the cause is LLM-side prefix-cache invalidation (#88) but cannot prove it from the JSON. With the breakdown surfaced we can confirm or falsify in one diff. **Fix:** in `loop()`, capture `t_obs_start = time.monotonic()` immediately before `build_observation`, `t_llm_start` immediately before `llm_client.chat`, and `t_dispatch_start` immediately before the tool-dispatch for-loop. Compute three deltas and pass them into `_record_step` as a dict `{"observation_ms": ..., "llm_ms": ..., "dispatch_ms": ...}` written under a new `step_breakdown[].latency_breakdown_ms` key. Sum invariant: `observation_ms + llm_ms + dispatch_ms` should equal `latency_ms` to within ±5 ms (allowing for the bookkeeping overhead). Tests: (1) unit test with stub LLM that sleeps 0.4 s and stub browser whose `build_observation` sleeps 0.1 s asserts `latency_breakdown_ms.llm_ms` is in `[350, 600]` and `observation_ms` is in `[80, 200]`; (2) sum invariant test asserts `abs((obs+llm+dispatch) - latency_ms) <= 5` for every step in a 5-step run; (3) JSON-schema test asserts every case in a fresh `eval/results/*.json` has `latency_breakdown_ms` populated with all three keys (no missing/null, even for the 0-step exception path). *Why useful:* this is the diagnostic prerequisite for evaluating #88's effect rigorously — without it, "the latency cliff went away" is a single-number observation, with it we can show the observation/dispatch components stayed flat while llm_ms came down. Also unlocks future tickets that target slow page observations independently. *Trigger:* 2026-04-29 user-driven webvoyager timeout investigation — surfaced when reviewing the `latency_ms_per_step` cliff and being unable to localize it.
