Generated from eval run: 2026-04-27T09:43:49.693513+00:00

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Inv. |
|---|---|---|---|---|---|---|---|---|
| correction-l1-miss-l2-hit | failed | 2 | 22909 | $0.0033 | 1892+695 | 0 | 0 | 0 |
| correction-replan | failed | 2 | 24779 | $0.0034 | 1916+763 | 0 | 0 | 0 |
| drift-submit-form-v1 | failed | 1 | 23271 | $0.0024 | 960+726 | 0 | 0 | 0 |
| drift-submit-form-v2 | failed | 1 | 23306 | $0.0024 | 960+726 | 0 | 0 | 0 |
| fixture-count | failed | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| fixture-heading | succeeded | 2 | 38303 | $0.0118 | 9954+925 | 0 | 0 | 0 |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| maintenance-drift-rename-v1 | failed | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| maintenance-drift-rename-v2 | failed | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |

**1/8 succeeded (12%)**

p50: 22909ms  p95: 38303ms

Total USD: $0.0234   Total tokens: 15682 prompt + 3835 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 0/8 |
| Replan | 0/8 |
| Cache invalidation | 0/8 |

Recorded at: 2026-04-27T09:43:49.693513+00:00
