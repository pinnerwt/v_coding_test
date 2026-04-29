---
id: 24
slug: multi-tool-call-last-action-preservation
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
related: []
filed_pr: null
merged_pr: null
archived_at: '2026-04-29'
trigger: Multi-tool-call `last_action` preservation in `loop.py`
---

24. **Multi-tool-call `last_action` preservation in `loop.py`** — when an LLM response carries N>1 tool calls, the loop overwrites `last_action` once per call so only the final one survives into the next observation; the earlier N-1 actions silently disappear from the model's view. Change `last_action` to carry the full ordered list of actions taken since the previous observation (e.g. `last_actions: [{tool, intent, outcome, error?}, ...]`, or keep `last_action` as the latest plus `prior_actions: [...]` for back-compat with `ObservationEvent`). Update `observe.build_observation` and `ObservationEvent` to accept the new shape. Tests: a single LLM response with two tool calls (`goto` then `read`) produces an observation on the next step whose `last_actions` contains both, in order; outcomes (`ok` / `error`) are preserved per-call; round-trip through `trace.py` JSON; single-call responses still produce a length-1 list (no regression in existing tests).
