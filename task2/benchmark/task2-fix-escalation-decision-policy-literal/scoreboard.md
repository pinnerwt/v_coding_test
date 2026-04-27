Generated from eval run: 2026-04-27T16:28:40.631091+00:00

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Inv. | Failure class |
|---|---|---|---|---|---|---|---|---|---|
| correction-l1-miss-l2-hit | failed | 2 | 30595 | $0.0037 | 1892+887 | 0 | 0 | 0 | no_done_emitted |
| correction-replan | failed | 2 | 22065 | $0.0032 | 1916+654 | 0 | 0 | 0 | no_done_emitted |
| drift-submit-form-v1 | failed | 5 | 58376 | $0.0123 | 9069+1604 | 0 | 0 | 0 | no_done_emitted |
| drift-submit-form-v2 | failed | 1 | 24454 | $0.0063 | 4978+686 | 0 | 0 | 0 | no_done_emitted |
| fixture-count | succeeded | 2 | 76367 | $0.0148 | 10468+2161 | 0 | 0 | 0 | - |
| fixture-heading | succeeded | 2 | 32450 | $0.0116 | 10018+801 | 1 | 0 | 0 | - |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| maintenance-drift-rename-v1 | failed | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | tool_error |
| maintenance-drift-rename-v2 | failed | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | tool_error |

**2/8 succeeded (25%)**

p50: 24454ms  p95: 76367ms

Total USD: $0.0519   Total tokens: 38341 prompt + 6793 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 1/8 |
| Replan | 0/8 |
| Cache invalidation | 0/8 |

Recorded at: 2026-04-27T16:28:40.631091+00:00
