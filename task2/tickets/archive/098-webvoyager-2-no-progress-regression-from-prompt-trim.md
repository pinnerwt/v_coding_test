---
id: 98
slug: webvoyager-2-no-progress-regression-from-prompt-trim
status: archived
tier: 5
urgency: P1
axes:
  pass_rate: 1
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence:
- task2/benchmark/task2-implement-prompt-trim-webvoyager-1/webvoyager/20260429_220514.json
- task2/benchmark/task2-audit-webvoyager-1-llm-dominance/webvoyager/20260429_211505.json
- task2/agent/loop.py
related:
- 97
- 99
filed_pr: 155
merged_pr: 155
archived_at: "2026-04-29"
trigger: "2026-04-29 — /done_pr aggregate-regression check on PR #154 (ticket #97 prompt-trim) found webvoyager-2 flipped from succeeded (10 steps, 115s) on baseline task2-audit-webvoyager-1-llm-dominance to failed (tool_error/no_progress, 8 steps, 105s); pass_rate 2/3 → 1/3"
---

98. **Restore webvoyager-2 pass after the prompt-trim regression — `trim_history` with default `HISTORY_TRIM_KEEP_STEPS=4` is too aggressive and triggers `no_progress` on 8+ step tasks.** webvoyager-2 was a passing case before #97 landed; with the new `trim_history` call wired into the loop it now fails at step 7 with `failure_class=tool_error` `failure_detail="unknown error"` and `reason="no_progress"`. The step_breakdown shows 4 consecutive `type` calls at steps 4-7 — the planner has lost the context of the earlier search/navigation steps (0-3, dropped from history once the keep_steps=4 window slides past them) and is re-typing the same form-fill action without recognizing the pattern. Prompt tokens grow 3K→15K across the 8 steps despite trimming, indicating the trim is dropping the *load-bearing* early-step context (where the search query was set up) while keeping recent stale `type` results that don't help disambiguate. **Goal:** reach pass on webvoyager-2 without losing the webvoyager-1 wins from #97 (steps 14→10, lat 125s→120s). Two candidate fixes (pick whichever the failing test localises): (a) raise default `HISTORY_TRIM_KEEP_STEPS` from 4 to 6 or 8 — keep more groups to preserve setup context on longer tasks; the trade-off is webvoyager-1's prompt growth returns, possibly re-tripping seconds_budget. (b) Make `trim_history` content-aware: never drop the *first* tool-result group (the initial `goto` + observation, which establishes the page state every later step depends on); this protects the "what page am I on" anchor without expanding the window. Likely (b) is the smaller-blast-radius fix. **Tests (TDD):**
- *Red:* extend `task2/tests/test_trim_history.py` with `test_trim_history_preserves_first_tool_group_when_window_smaller` — build messages with 6 groups, call `trim_history(messages, keep_steps=2)`, assert the *first* tool-result group's `tool_call_id` is present in the output (in addition to the most recent 2). Currently the implementation drops it.
- *Green:* update `trim_history` to mark group index 0 as always-keep, then drop oldest groups from `[1:N-keep_steps]` rather than `[0:N-keep_steps]`.
- *Benchmark gate (manual, post-merge in `/done_pr`):* webvoyager-2 SHALL pass in ≥2 of 3 fresh runs; webvoyager-1 SHALL NOT regress on `steps` or `latency_ms_total` vs the #97 baseline.

**Done bar:** unit tests green; smoke test pass; the post-merge `/done_pr` benchmark capture shows pass_rate ≥ 2/3 (i.e. recovers webvoyager-2) with webvoyager-1 still at ≤120s wall-clock. *Why useful:* tier 5 pass-rate-led — the suite is at 1/3 right now and the dominant single fix to get back to 2/3 is recovering webvoyager-2; webvoyager-1 itself is still owned by a separate next-iteration ticket since prompt-trim alone didn't bring it under budget. *Trigger:* /done_pr's aggregate-regression check on PR #154 caught the flip; without that check #97 would have shipped silent and the next iteration's scoreboard read would have been confused by an unexplained -33% pass-rate drop.
