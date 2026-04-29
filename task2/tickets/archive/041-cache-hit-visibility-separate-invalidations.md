---
id: 41
slug: cache-hit-visibility-separate-invalidations
status: archived
tier: 4
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related:
- 29
filed_pr: 82
merged_pr: null
archived_at: '2026-04-29'
trigger: Cache-hit visibility separate from invalidations.
---

41. **Cache-hit visibility separate from invalidations.** Current "Cache Inv." column shows invalidation count only. Add a `Cache Hits` and `Cache Misses` column populated from `cache_events.{hits,misses}` (already aggregated by `_aggregate_diagnostics` per ticket #29). Lets us see whether the cache is actually serving traffic vs. always cold. Tests: a two-step case that resolves the same intent twice shows `hits=1, misses=1, invalidations=0`; a drift case shows `invalidations >= 1`.
