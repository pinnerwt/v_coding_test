Generated from eval run: 2026-04-27T10:27:04.469937+00:00

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Inv. |
|---|---|---|---|---|---|---|---|---|
| correction-l1-miss-l2-hit | failed | 2 | 24601 | $0.0033 | 1892+702 | 0 | 0 | 0 |
| correction-replan | failed | 2 | 66711 | $0.0060 | 2000+1983 | 0 | 0 | 0 |
| drift-submit-form-v1 | failed | 3 | 41160 | $0.0057 | 3419+1159 | 0 | 0 | 0 |
| drift-submit-form-v2 | failed | 3 | 42626 | $0.0081 | 5790+1145 | 0 | 0 | 0 |
| fixture-count | succeeded | 2 | 29110 | $0.0051 | 3553+778 | 0 | 0 | 0 |
| fixture-heading | succeeded | 2 | 24804 | $0.0048 | 3463+655 | 0 | 0 | 0 |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 |
| maintenance-drift-rename-v1 | failed | 1 | 24075 | $0.0030 | 1724+660 | 0 | 0 | 0 |
| maintenance-drift-rename-v2 | failed | 1 | 29982 | $0.0034 | 1724+860 | 0 | 0 | 0 |

**2/8 succeeded (25%)**

p50: 29110ms  p95: 66711ms

Total USD: $0.0394   Total tokens: 23565 prompt + 7942 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 0/8 |
| Replan | 0/8 |
| Cache invalidation | 0/8 |

Recorded at: 2026-04-27T10:27:04.469937+00:00
