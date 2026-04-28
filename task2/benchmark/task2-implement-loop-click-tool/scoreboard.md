Generated from eval run: 2026-04-28T10:58:52.166708+00:00

Drift suite: 6/6 (100%) [target 100%] ✅
Fixture: 2/2 (100%) [target 80%] ✅
Live: 0/0 ran [target 60%] ⏭️

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Hits | Cache Misses | Cache Inv. | Failure class |
|---|---|---|---|---|---|---|---|---|---|---|---|
| canary-read-h1 | succeeded | 3 | 27300 | $0.0054 | 3664+843 | 1 | 0 | 0 | 2 | 0 | - |
| correction-l1-miss-l2-hit | succeeded | 4 | 21210 | $0.0063 | 5124+607 | 2 | 0 | 0 | 3 | 0 | - |
| correction-replan | succeeded | 3 | 21731 | $0.0050 | 3745+638 | 0 | 0 | 0 | 0 | 0 | - |
| drift-submit-form-v1 | succeeded | 2 | 17332 | $0.0032 | 2209+519 | 0 | 0 | 0 | 0 | 0 | - |
| drift-submit-form-v2 | succeeded | 4 | 22670 | $0.0066 | 5300+663 | 1 | 0 | 0 | 1 | 0 | - |
| fixture-count | succeeded | 3 | 21836 | $0.0051 | 3764+662 | 1 | 0 | 0 | 2 | 0 | - |
| fixture-heading | succeeded | 3 | 28821 | $0.0054 | 3601+876 | 1 | 0 | 0 | 2 | 0 | - |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| maintenance-drift-rename-v1 | succeeded | 2 | 15667 | $0.0032 | 2209+473 | 0 | 0 | 0 | 0 | 0 | - |
| maintenance-drift-rename-v2 | succeeded | 2 | 20763 | $0.0035 | 2209+653 | 0 | 0 | 0 | 0 | 0 | - |

**Skipped** (5 cases)

| Skip reason | Count |
|---|---|
| live_disabled | 5 |

**9/9 succeeded (100%)**

p50: 21731ms  p95: 28821ms

Total USD: $0.0437   Total tokens: 31825 prompt + 5934 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 5/9 |
| Replan | 0/9 |
| Cache invalidation | 0/9 |

Recorded at: 2026-04-28T10:58:52.166708+00:00
