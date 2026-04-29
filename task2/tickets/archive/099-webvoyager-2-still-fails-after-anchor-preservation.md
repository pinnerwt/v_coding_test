---
id: 99
slug: webvoyager-2-still-fails-after-anchor-preservation
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
- task2/benchmark/task2-fix-trim-history-preserve-first-group/webvoyager/20260429_225802.json
- task2/benchmark/task2-implement-prompt-trim-webvoyager-1/webvoyager/20260429_220514.json
related:
- 98
- 97
filed_pr: 156
merged_pr: 156
archived_at: "2026-04-29"
trigger: "2026-04-29 — /done_pr post-merge benchmark capture for ticket #98 (anchor-preservation fix); webvoyager-2 still fails after the fix shipped, with failure mode shifted from `tool_error/no_progress` (8 steps, 105s) to `tool_error 'unknown error'` (5 steps, 54s); pass_rate stays at 1/3"
---

99. **Diagnose why webvoyager-2 still fails after anchor preservation — `tool_error 'unknown error'` at step 4 in a 5-step trace, with all of `goto`/`type`/`click`/`click`/`click` issued correctly.** Ticket #98 hypothesized that `trim_history` evicting the chronologically-earliest tool-result group (the page-establishing `goto`) caused webvoyager-2's `no_progress` failure at step 7+, and the fix preserved group 0 unconditionally. The fix shipped (PR #155) and aggregate axes improved (-22% across cost/tokens/latency) but webvoyager-2 still fails — pass_rate remains 1/3. The new trace shows the case dies earlier (step 4) with `failure_class=tool_error` and `failure_detail='unknown error'`. step_breakdown is `goto → type → click → click → click` with monotonically increasing prompt_tokens (3K → 5K → 8K → 10K → 13K), so anchor preservation is working — the planner is making forward progress and not repeating type calls — but something in the click sequence on the live page raises an opaque error that surfaces as `tool_error/unknown error` and terminates the run. **Goal:** identify what raises "unknown error" at step 4 of webvoyager-2 and either (a) classify it under a more specific `failure_class` so the next ticket has a real signal, or (b) fix the underlying browser/tool-dispatch path. **Tests (TDD):**
- *Red:* extend `task2/tests/test_browser.py` (or the appropriate test file owning the click dispatch path) with a test that reproduces the "unknown error" string surfacing as `failure_detail` — likely an exception in `agent/browser.py:Browser.click` or `agent/loop.py` that gets stringified as plain `'unknown error'` instead of including the original exception class+message. Assert that the stringified failure_detail starts with the exception class name (e.g. `TimeoutError(...)`, `LocatorError(...)`).
- *Green:* fix the exception-stringification path so `failure_detail` carries the underlying class+message, OR fix the root cause of the click failure if the diagnostic surfaces it.
- *Benchmark gate (manual, post-merge in `/done_pr`):* webvoyager-2 SHALL either (i) succeed in ≥2 of 3 fresh runs, OR (ii) fail with a concrete `failure_class != "tool_error"` and a `failure_detail` carrying a real exception trace, so the next iteration's ticket has actionable signal.

**Done bar:** unit tests green; smoke test pass; the post-merge `/done_pr` benchmark capture shows either webvoyager-2 succeeded (recovering pass_rate to 2/3) OR webvoyager-2 failure has a concrete classified `failure_class` and exception-bearing `failure_detail`. *Why useful:* tier 5 pass-rate-led — webvoyager-2 was the dominant single fix to get pass_rate from 1/3 to 2/3, and #98's hypothesis was disproved (anchor preservation alone is not the cause); without a concrete failure signal the next iteration will keep guessing. *Trigger:* /done_pr's benchmark capture for PR #155 surfaced that #98's done-bar (pass_rate ≥ 2/3) was not met despite the fix shipping correctly per spec.
