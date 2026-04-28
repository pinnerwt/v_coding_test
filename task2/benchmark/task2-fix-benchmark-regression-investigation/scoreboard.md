Generated from eval run: 2026-04-28T03:37:22.862151+00:00

Drift suite: 0/6 (0%) [target 100%] ❌
Fixture: 0/2 (0%) [target 80%] ❌
Live: 0/0 ran [target 60%] ⏭️

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Inv. | Failure class |
|---|---|---|---|---|---|---|---|---|---|
| correction-l1-miss-l2-hit | failed | 2 | 24242 | $0.0033 | 1892+711 | 0 | 0 | 0 | no_done_emitted |
| correction-replan | failed | 2 | 29063 | $0.0037 | 1916+876 | 0 | 0 | 0 | no_done_emitted |
| drift-submit-form-v1 | failed | 1 | 20694 | $0.0022 | 960+629 | 0 | 0 | 0 | no_done_emitted |
| drift-submit-form-v2 | failed | 1 | 20754 | $0.0022 | 960+629 | 0 | 0 | 0 | no_done_emitted |
| fixture-count | failed | 2 | 24907 | $0.0034 | 1922+742 | 0 | 0 | 0 | no_done_emitted |
| fixture-heading | failed | 2 | 33250 | $0.0040 | 1982+999 | 1 | 0 | 0 | locator_miss |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| maintenance-drift-rename-v1 | failed | 1 | 25345 | $0.0026 | 960+797 | 0 | 0 | 0 | no_done_emitted |
| maintenance-drift-rename-v2 | failed | 1 | 24246 | $0.0025 | 960+786 | 0 | 0 | 0 | no_done_emitted |

**Skipped** (5 cases)

| Skip reason | Count |
|---|---|
| live_disabled | 5 |

**0/8 succeeded (0%)**

p50: 24246ms  p95: 33250ms

Total USD: $0.0239   Total tokens: 11552 prompt + 6169 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 1/8 |
| Replan | 0/8 |
| Cache invalidation | 0/8 |

Recorded at: 2026-04-28T03:37:22.862151+00:00
