---
id: 21
slug: observe-py-ax-tree-observation
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
filed_pr: 38
merged_pr: null
archived_at: '2026-04-29'
trigger: '`observe.py` AX-tree observation'
---

21. **`observe.py` AX-tree observation** — replace `loop.py`'s `body.innerText[:2000]` observation with a trimmed accessibility tree (interactable nodes only: button, link, textbox, combobox, checkbox, radio, tab, menuitem, option, plus headings) + URL + title + last-action result `{tool, intent, outcome, error?}`. Cap total node count and accessible-name length to bound tokens. Populates `ObservationEvent.ax_tree_digest` (already in trace schema). Tests: fixture with decorative `<div>`s + real `<button>`s → observation contains buttons only; 1000-button page → node count capped; second step threads previous `last_action`, first step has `last_action: null`; `ax_tree_digest` round-trips through `trace.py` with serialized roles.
