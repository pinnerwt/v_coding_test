---
id: 62
slug: pre-flight-fail-validation-gate-agent
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
- 59
- 60
- 61
filed_pr: 96
merged_pr: null
archived_at: '2026-04-29'
trigger: surfaced from benchmark analysis on 2026-04-28; the read→fail shape is the
  same across 5 cases, suggesting prompt + tool fix may not be sufficient on its own
  without a structural guardrail.
---

62. **Pre-flight `fail` validation gate in the agent loop.** When the model emits `fail` on step ≤ 1 of a budget-N run with no prior `read` evidence covering the target intent, the loop should reject the call and return a one-line supervisor nudge: "you have N-1 steps left and have not attempted to interact — try `click`/`type` first." This is a soft guardrail against premature give-up; the L1-miss-L2-hit case should never see step-2 `fail` if L1 even found candidate elements. Implementation: in `agent/loop.py`'s tool-dispatch branch for `fail`, check `(step_num <= 1 and not any(_has_actionable_outcome(e) for e in events))`; if true, do not terminate the run — instead emit a `SupervisorEvent(classified_as="premature_fail")` and continue the loop. The classifier literal `premature_fail` is added to `agent/trace.py:SupervisorEventClass`. Tests: (a) synthetic LLM stub that emits `fail` on step 1 → loop emits a `SupervisorEvent(classified_as="premature_fail")`, the run does not terminate, and the next prompt to the model includes the nudge string; (b) a `fail` after step 1 with at least one prior `click`/`type` attempt is honored normally; (c) a `fail` with reason matching the irrecoverable-condition list (e.g. "login wall") is honored on any step. *Why useful:* keeps the agent inside its budget instead of bailing on partial information; complements #59/#60/#61 by catching the "model gave up anyway" residual mode. *Trigger:* surfaced from benchmark analysis on 2026-04-28; the read→fail shape is the same across 5 cases, suggesting prompt + tool fix may not be sufficient on its own without a structural guardrail.
