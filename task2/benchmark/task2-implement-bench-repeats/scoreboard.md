Generated from eval run: 2026-04-28T01:46:06.913948+00:00

Drift suite: 0/6 (0%) [target 100%] ❌
Fixture: 0/2 (0%) [target 80%] ❌
Live: 0/0 ran [target 60%] ⏭️

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Inv. | Failure class |
|---|---|---|---|---|---|---|---|---|---|
| correction-l1-miss-l2-hit | failed | 2 | 24364 | $0.0033 | 1892+711 | 0 | 0 | 0 | no_done_emitted |
| correction-replan | failed | 2 | 26139 | $0.0034 | 1916+766 | 0 | 0 | 0 | no_done_emitted |
| drift-submit-form-v1 | failed | 1 | 20623 | $0.0022 | 960+629 | 0 | 0 | 0 | no_done_emitted |
| drift-submit-form-v2 | failed | 1 | 20150 | $0.0022 | 960+629 | 0 | 0 | 0 | no_done_emitted |
| fixture-count | failed | 2 | 24117 | $0.0034 | 1922+742 | 0 | 0 | 0 | no_done_emitted |
| fixture-heading | failed | 2 | 32150 | $0.0040 | 1982+999 | 1 | 0 | 0 | locator_miss |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| maintenance-drift-rename-v1 | failed | 1 | 25761 | $0.0026 | 960+797 | 0 | 0 | 0 | no_done_emitted |
| maintenance-drift-rename-v2 | failed | 1 | 26145 | $0.0025 | 960+786 | 0 | 0 | 0 | no_done_emitted |

**Skipped** (5 cases)

| Skip reason | Count |
|---|---|
| live_disabled | 5 |

**0/8 succeeded (0%)**

p50: 24364ms  p95: 32150ms

Total USD: $0.0237   Total tokens: 11552 prompt + 6059 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 1/8 |
| Replan | 0/8 |
| Cache invalidation | 0/8 |

Recorded at: 2026-04-28T01:46:06.913948+00:00
