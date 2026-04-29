---
id: 47
slug: tighten-escalationdecision-policy-same-literal-supervisorevent
status: archived
tier: 5
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related:
- 62
filed_pr: null
merged_pr: null
archived_at: '2026-04-29'
trigger: 'surfaced by review subagents on PR #62 (iterations 2 and 3); iteration 2
  deferred it as out of scope.'
---

47. **Tighten `EscalationDecision.policy` to the same `Literal` as `SupervisorEvent.policy`.** `agent/supervisor.py:17` types `EscalationDecision.policy` as plain `str`, but `agent/trace.py:80` types `SupervisorEvent.policy` as `Literal["next_tier", "rerank", "sweep_overlay", "replan", "halt"]`. The mismatch forces a `# type: ignore[arg-type]` in `_emit_supervisor_event` (`agent/loop.py`). Tightening `EscalationDecision.policy` to the same `Literal` enforces the contract end-to-end at type-check time and removes the suppression. Touch all call sites in `Supervisor.handle` (`agent/supervisor.py`) so they construct `EscalationDecision` with literal values, and update unit tests in `tests/test_supervisor.py` to type-check against the new alias. Tests: existing `test_supervisor.py` continues to pass; a mypy / ruff run shows no `arg-type` suppression remaining in `_emit_supervisor_event`. *Why useful:* removes a real type-narrowing gap and a `# type: ignore` line. *Trigger:* surfaced by review subagents on PR #62 (iterations 2 and 3); iteration 2 deferred it as out of scope.
