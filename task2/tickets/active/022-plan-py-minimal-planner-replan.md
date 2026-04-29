---
id: 22
slug: plan-py-minimal-planner-replan
status: active
tier: 5
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related: []
filed_pr: null
merged_pr: null
archived_at: null
trigger: ''
---

22. **`plan.py` minimal planner + replan** — new module with `plan(task, observation, llm) -> Plan{steps, expected_end_state}` and `replan(task, observation, prior_plan, reason, llm) -> Plan`. Loop calls `plan()` once after the first observation and emits `PlanEvent(reason="initial")` (schema already defined). Each subsequent decision prompt includes a "Plan progress" block with remaining steps. Supervisor `halt` triggers one `replan()` (emit `PlanEvent(reason="replan")`) before declaring `failed`; cap at 1 replan per run. Tests: loop on fixture emits `PlanEvent` before any `DecisionEvent`; mock LLM sees plan steps in step-1+ user message; halt → replan → continue; second halt after replan → real fail (no infinite loop).
