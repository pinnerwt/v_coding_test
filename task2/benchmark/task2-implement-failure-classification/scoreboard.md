Generated from eval run: 2026-04-27T12:52:01.543725+00:00

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Inv. | Failure class |
|---|---|---|---|---|---|---|---|---|---|
| correction-l1-miss-l2-hit | failed | 2 | 23836 | $0.0033 | 1892+700 | 0 | 0 | 0 | no_done_emitted |
| correction-replan | failed | 2 | 23847 | $0.0034 | 1916+724 | 0 | 0 | 0 | no_done_emitted |
| drift-submit-form-v1 | failed | 1 | 20491 | $0.0022 | 960+632 | 0 | 0 | 0 | no_done_emitted |
| drift-submit-form-v2 | failed | 1 | 20422 | $0.0022 | 960+632 | 0 | 0 | 0 | no_done_emitted |
| fixture-count | failed | 2 | 29273 | $0.0037 | 1922+900 | 0 | 0 | 0 | no_done_emitted |
| fixture-heading | unverified | 2 | 56796 | $0.0055 | 2006+1767 | 0 | 0 | 0 | - |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| maintenance-drift-rename-v1 | failed | 2 | 22327 | $0.0033 | 1904+679 | 0 | 0 | 0 | no_done_emitted |
| maintenance-drift-rename-v2 | failed | 2 | 22392 | $0.0033 | 1904+679 | 0 | 0 | 0 | no_done_emitted |

**1/8 succeeded (12%)**

p50: 22392ms  p95: 56796ms

Total USD: $0.0269   Total tokens: 13464 prompt + 6713 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 0/8 |
| Replan | 0/8 |
| Cache invalidation | 0/8 |

Recorded at: 2026-04-27T12:52:01.543725+00:00
