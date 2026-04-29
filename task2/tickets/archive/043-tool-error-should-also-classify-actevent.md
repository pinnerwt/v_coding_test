---
id: 43
slug: tool-error-should-also-classify-actevent
status: archived
tier: 2
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related:
- 31
filed_pr: null
merged_pr: null
archived_at: '2026-04-29'
trigger: '`tool_error` should also classify `ActEvent(outcome="timeout")`.'
---

43. **`tool_error` should also classify `ActEvent(outcome="timeout")`.** `agent/trace.py:69` types `ActEvent.outcome` as `Literal["ok", "no_effect", "nav", "timeout", "error"]`, but `_classify_failure` in `scripts/eval.py` (added in ticket #31) only catches `outcome="error"`. A failed case whose only signal is a Playwright timeout (e.g. `wait_for` exhausted) currently falls through to `no_done_emitted`, which loses the more specific signal that the browser tool stalled. Decision needed: (a) widen the predicate to `outcome in {"error", "timeout"}` and treat both as `tool_error`, OR (b) introduce a new `failure_class="tool_timeout"` literal (and a new column option in the scoreboard). Tests: synthetic `ActEvent(outcome="timeout")` with status="failed" classifies as the chosen literal; the existing `ActEvent(outcome="error")` test still classifies as `tool_error`; design.md / spec rule 2.c updated to match the chosen direction.
