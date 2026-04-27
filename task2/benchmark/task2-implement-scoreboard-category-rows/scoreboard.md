Generated from eval run: 2026-04-27T17:10:42.998402+00:00

Drift suite: 0/6 (0%) [target 100%] ❌
Fixture: 0/2 (0%) [target 80%] ❌
Live: 0/0 ran [target 60%] ⏭️

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Inv. | Failure class |
|---|---|---|---|---|---|---|---|---|---|
| correction-l1-miss-l2-hit | failed | 2 | 19541 | $0.0031 | 1892+583 | 0 | 0 | 0 | no_done_emitted |
| correction-replan | failed | 2 | 33226 | $0.0039 | 1916+989 | 0 | 0 | 0 | no_done_emitted |
| drift-submit-form-v1 | failed | 1 | 19217 | $0.0021 | 960+591 | 0 | 0 | 0 | no_done_emitted |
| drift-submit-form-v2 | failed | 1 | 19550 | $0.0021 | 960+591 | 0 | 0 | 0 | no_done_emitted |
| fixture-count | failed | 2 | 24281 | $0.0034 | 1922+725 | 0 | 0 | 0 | no_done_emitted |
| fixture-heading | failed | 2 | 53717 | $0.0053 | 2028+1644 | 1 | 0 | 0 | locator_miss |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| maintenance-drift-rename-v1 | failed | 1 | 22271 | $0.0023 | 960+687 | 0 | 0 | 0 | no_done_emitted |
| maintenance-drift-rename-v2 | failed | 1 | 22666 | $0.0023 | 960+687 | 0 | 0 | 0 | no_done_emitted |

**0/8 succeeded (0%)**

p50: 22271ms  p95: 53717ms

Total USD: $0.0246   Total tokens: 11598 prompt + 6497 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 1/8 |
| Replan | 0/8 |
| Cache invalidation | 0/8 |

Recorded at: 2026-04-27T17:10:42.998402+00:00
