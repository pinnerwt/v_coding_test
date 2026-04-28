Generated from eval run: 2026-04-28T00:22:43.744167+00:00

Drift suite: 0/6 (0%) [target 100%] ❌
Fixture: 1/2 (50%) [target 80%] ❌
Live: 0/0 ran [target 60%] ⏭️

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Inv. | Failure class |
|---|---|---|---|---|---|---|---|---|---|
| correction-l1-miss-l2-hit | failed | 2 | 25598 | $0.0033 | 1892+696 | 0 | 0 | 0 | no_done_emitted |
| correction-replan | failed | 2 | 27169 | $0.0034 | 1916+726 | 0 | 0 | 0 | no_done_emitted |
| drift-submit-form-v1 | failed | 1 | 26884 | $0.0024 | 960+735 | 0 | 0 | 0 | no_done_emitted |
| drift-submit-form-v2 | failed | 1 | 27089 | $0.0024 | 960+735 | 0 | 0 | 0 | no_done_emitted |
| fixture-count | unverified | 2 | 29854 | $0.0036 | 1922+838 | 0 | 0 | 0 | - |
| fixture-heading | failed | 2 | 32251 | $0.0039 | 1982+936 | 1 | 0 | 0 | locator_miss |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| maintenance-drift-rename-v1 | failed | 2 | 34724 | $0.0039 | 1904+973 | 0 | 0 | 0 | no_done_emitted |
| maintenance-drift-rename-v2 | failed | 2 | 34792 | $0.0039 | 1904+973 | 0 | 0 | 0 | no_done_emitted |

**Skipped** (5 cases)

| Skip reason | Count |
|---|---|
| live_disabled | 5 |

**1/8 succeeded (12%)**

p50: 27169ms  p95: 34792ms

Total USD: $0.0267   Total tokens: 13440 prompt + 6612 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 1/8 |
| Replan | 0/8 |
| Cache invalidation | 0/8 |

Recorded at: 2026-04-28T00:22:43.744167+00:00
