---
id: 13
slug: trace-replay-harness
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
filed_pr: 23
merged_pr: null
archived_at: null
trigger: ''
---

13. **Trace replay harness** — feed a recorded `LLMCallEvent.prompt` sequence into `loop.py` with the live browser stubbed; assert produced `DecisionEvent`s match the recording. This is the regression test surface for prompt/policy changes.
