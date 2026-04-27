Generated from eval run: 2026-04-27T08:03:29.240528+00:00

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Inv. |
|---|---|---|---|---|---|---|---|---|
| correction-l1-miss-l2-hit | failed | 2 | 23952 | $0.0033 | 1892+720 | 0 | 0 | 0 |
| correction-replan | failed | 2 | 26314 | $0.0035 | 1916+804 | 0 | 0 | 0 |
| drift-submit-form-v1 | failed | 1 | 20434 | $0.0022 | 960+629 | 0 | 0 | 0 |
| drift-submit-form-v2 | failed | 1 | 20508 | $0.0022 | 960+629 | 0 | 0 | 0 |
| fixture-count | failed | 2 | 30166 | $0.0037 | 1922+876 | 0 | 0 | 0 |
| fixture-heading | failed | 3 | 35917 | $0.0052 | 3158+1040 | 0 | 0 | 0 |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| maintenance-drift-rename-v1 | failed | 2 | 30155 | $0.0037 | 1904+882 | 0 | 0 | 0 |
| maintenance-drift-rename-v2 | failed | 1 | 27008 | $0.0025 | 960+778 | 0 | 0 | 0 |

**0/8 succeeded (0%)**

p50: 26314ms  p95: 35917ms

Total USD: $0.0264   Total tokens: 13672 prompt + 6358 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 0/8 |
| Replan | 0/8 |
| Cache invalidation | 0/8 |

Recorded at: 2026-04-27T08:03:29.240528+00:00
