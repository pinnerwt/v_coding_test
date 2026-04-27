Generated from eval run: 2026-04-27T11:47:45.242604+00:00

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Inv. |
|---|---|---|---|---|---|---|---|---|
| correction-l1-miss-l2-hit | failed | 2 | 26206 | $0.0033 | 1892+702 | 0 | 0 | 0 |
| correction-replan | failed | 2 | 32017 | $0.0037 | 1916+880 | 0 | 0 | 0 |
| drift-submit-form-v1 | failed | 2 | 29090 | $0.0036 | 1904+829 | 0 | 0 | 0 |
| drift-submit-form-v2 | failed | 2 | 27607 | $0.0036 | 1904+829 | 0 | 0 | 0 |
| fixture-count | failed | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| fixture-heading | succeeded | 4 | 53907 | $0.0294 | 27035+1195 | 0 | 0 | 0 |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| maintenance-drift-rename-v1 | failed | 2 | 37369 | $0.0122 | 10344+906 | 0 | 0 | 0 |
| maintenance-drift-rename-v2 | failed | 2 | 38152 | $0.0122 | 10344+942 | 0 | 0 | 0 |

**1/8 succeeded (12%)**

p50: 29090ms  p95: 53907ms

Total USD: $0.0679   Total tokens: 55339 prompt + 6283 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 0/8 |
| Replan | 0/8 |
| Cache invalidation | 0/8 |

Recorded at: 2026-04-27T11:47:45.242604+00:00
