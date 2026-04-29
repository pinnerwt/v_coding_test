---
id: 34
slug: skip-reason-tagging
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
related: []
filed_pr: 73
merged_pr: null
archived_at: '2026-04-29'
trigger: Skip-reason tagging.
---

34. **Skip-reason tagging.** Add `skip_reason: Literal["live_disabled", "infra_unavailable", "fixture_missing", "feature_not_implemented"] | None` to `CaseResult` and require it whenever `status="skipped"`. Wire `eval.py`'s skip path to set it (currently every skip is anonymous). Surface in the scoreboard as a "Skipped" subsection with reason counts. Tests: a run with `--no-live` produces `skip_reason="live_disabled"` for live cases; a missing fixture file produces `skip_reason="fixture_missing"`; an unrecognized reason is rejected at construction time.
