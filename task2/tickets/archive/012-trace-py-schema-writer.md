---
id: 12
slug: trace-py-schema-writer
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
merged_pr: 18
archived_at: '2026-04-25'
trigger: '`trace.py` schema + writer'
---

12. **`trace.py` schema + writer** — round-trip a `Run` + each `Event` variant through JSON; `seq` strictly increasing; redaction of secret-typed fields verified.
