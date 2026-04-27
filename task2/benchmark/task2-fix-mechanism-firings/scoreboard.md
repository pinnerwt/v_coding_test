Generated from eval run: 2026-04-27T14:32:18.032995+00:00

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Inv. | Failure class |
|---|---|---|---|---|---|---|---|---|---|
| correction-l1-miss-l2-hit | failed | 2 | 28597 | $0.0036 | 1892+874 | 0 | 0 | 0 | no_done_emitted |
| correction-replan | failed | 2 | 27844 | $0.0037 | 1916+881 | 0 | 0 | 0 | no_done_emitted |
| drift-submit-form-v1 | failed | 2 | 25127 | $0.0035 | 1904+789 | 0 | 0 | 0 | no_done_emitted |
| drift-submit-form-v2 | failed | 2 | 25067 | $0.0035 | 1904+789 | 0 | 0 | 0 | no_done_emitted |
| fixture-count | failed | 2 | 28610 | $0.0037 | 1922+904 | 0 | 0 | 0 | no_done_emitted |
| fixture-heading | unverified | 3 | 30719 | $0.0051 | 3158+959 | 1 | 0 | 0 | - |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| maintenance-drift-rename-v1 | failed | 4 | 46279 | $0.0093 | 6865+1242 | 0 | 0 | 0 | no_done_emitted |
| maintenance-drift-rename-v2 | failed | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | tool_error |

**1/8 succeeded (12%)**

p50: 27844ms  p95: 46279ms

Total USD: $0.0324   Total tokens: 19561 prompt + 6438 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 1/8 |
| Replan | 0/8 |
| Cache invalidation | 0/8 |

Recorded at: 2026-04-27T14:32:18.032995+00:00
