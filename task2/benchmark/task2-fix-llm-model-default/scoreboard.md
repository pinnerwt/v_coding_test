Generated from eval run: 2026-04-27T15:14:57.745592+00:00

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Inv. | Failure class |
|---|---|---|---|---|---|---|---|---|---|
| correction-l1-miss-l2-hit | failed | 2 | 22948 | $0.0032 | 1892+648 | 0 | 0 | 0 | no_done_emitted |
| correction-replan | unverified | 3 | 44415 | $0.0060 | 3454+1262 | 1 | 0 | 0 | - |
| drift-submit-form-v1 | timeout | 5 | 48888 | $0.0137 | 11343+1190 | 0 | 0 | 0 | - |
| drift-submit-form-v2 | failed | 3 | 52230 | $0.0071 | 4179+1467 | 1 | 0 | 0 | locator_miss |
| fixture-count | succeeded | 2 | 36814 | $0.0046 | 2588+1024 | 0 | 0 | 0 | - |
| fixture-heading | succeeded | 3 | 40096 | $0.0064 | 4175+1097 | 1 | 0 | 0 | - |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| maintenance-drift-rename-v1 | timeout | 5 | 65032 | $0.0123 | 8702+1785 | 1 | 0 | 0 | - |
| maintenance-drift-rename-v2 | failed | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | tool_error |

**3/8 succeeded (37%)**

p50: 40096ms  p95: 65032ms

Total USD: $0.0533   Total tokens: 36333 prompt + 8473 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 4/8 |
| Replan | 0/8 |
| Cache invalidation | 0/8 |

Recorded at: 2026-04-27T15:14:57.745592+00:00
