---
id: 32
slug: audit-ticket-investigate-why-mechanism-firing
status: archived
tier: 4
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related:
- 28
filed_pr: 62
merged_pr: 62
archived_at: '2026-04-27'
trigger: 'Audit ticket: investigate why mechanism-firing rates are 0/8 on diagnostic
  cases.'
---

32. **Audit ticket: investigate why mechanism-firing rates are 0/8 on diagnostic cases.** Not a feature — a debug ticket. The unit tests in `test_eval.py:test_run_suite_*` assert `escalations`, `replans`, `cache_events` populate for the diagnostic cases; the live benchmark shows 0. Reproduce locally with the real `loop()` + a real (or scripted) Qwen client, capture the trace, identify which event(s) are missing or whose `policy`/`reason`/`cache_action` field doesn't match what `_aggregate_diagnostics` expects, and fix the gap. Possible suspects: (a) `loop()` doesn't actually call the locator escalation path the same way the unit-test mock does; (b) `SupervisorEvent.policy` is being set to something other than `"next_tier"` in real runs; (c) cache `invalidate` action is never emitted because the cache is never warm across v1→v2 in production runs (ticket #28 was supposed to fix this — verify it actually landed end-to-end). Done bar: at least one of `correction-l1-miss-l2-hit`, `correction-replan`, `maintenance-drift-rename-v2` shows non-zero firings on a real run, and a test that *runs the real loop* (not just the mock) asserts it.
