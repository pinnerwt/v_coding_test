Generated from eval run: 2026-04-27T15:50:14.730503+00:00

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Inv. | Failure class |
|---|---|---|---|---|---|---|---|---|---|
| correction-l1-miss-l2-hit | failed | 2 | 23524 | $0.0033 | 1892+705 | 0 | 0 | 0 | no_done_emitted |
| correction-replan | failed | 2 | 29177 | $0.0037 | 1916+889 | 0 | 0 | 0 | no_done_emitted |
| drift-submit-form-v1 | failed | 4 | 51489 | $0.0132 | 10459+1392 | 0 | 0 | 0 | no_done_emitted |
| drift-submit-form-v2 | failed | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | tool_error |
| fixture-count | succeeded | 2 | 71892 | $0.0144 | 10468+1947 | 0 | 0 | 0 | - |
| fixture-heading | succeeded | 3 | 44962 | $0.0197 | 17731+1000 | 1 | 0 | 0 | - |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| maintenance-drift-rename-v1 | failed | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | tool_error |
| maintenance-drift-rename-v2 | failed | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | tool_error |

**2/8 succeeded (25%)**

p50: 23524ms  p95: 71892ms

Total USD: $0.0543   Total tokens: 42466 prompt + 5933 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 1/8 |
| Replan | 0/8 |
| Cache invalidation | 0/8 |

Recorded at: 2026-04-27T15:50:14.730503+00:00
