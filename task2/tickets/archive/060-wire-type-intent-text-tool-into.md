---
id: 60
slug: wire-type-intent-text-tool-into
status: archived
tier: 5
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies:
- 59
pre_flight_gates: []
evidence: []
related:
- 56
filed_pr: 91
merged_pr: null
archived_at: '2026-04-29'
trigger: 'surfaced from same benchmark analysis as #59 on 2026-04-28; smaller red→green
  flip count today (no current case requires `type` *before* `click`), but closes
  the obvious next failure mode after #59 lands.'
---

60. **Wire `type(intent, text)` tool into `agent/loop.py`.** Same pattern as #59 but resolves a textbox role and calls `loc.fill(text)`. Tools list adds `type(intent: str, text: str)`. The `read` path's existing intent grammar already supports textbox role tokens (recently widened by #56's alias map). Without this tool, any task that requires filling a form field before submitting is unreachable — currently masked by #59's absence (the agent gives up at the click step), but will surface as soon as #59 lands and the eval suite gets a "fill `email` then submit" case (or once `live-form-fill` is enabled). Tests: (a) `_TOOLS` includes a `type` entry with `intent: str` and `text: str`; (b) fixture-page test fills a textbox identified by intent and asserts the resulting `<input>.value`; (c) `LocatorMiss` on a non-textbox intent returns a tool error the model can recover from (does not auto-`fail` the run). *Why useful:* unblocks the form-fill class of cases (`live-form-fill`, future `correction-form-fill-*` drift fixtures). *Trigger:* surfaced from same benchmark analysis as #59 on 2026-04-28; smaller red→green flip count today (no current case requires `type` *before* `click`), but closes the obvious next failure mode after #59 lands.
