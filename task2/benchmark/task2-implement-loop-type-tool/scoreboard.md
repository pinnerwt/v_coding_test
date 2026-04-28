Generated from eval run: 2026-04-28T11:48:02.396305+00:00

Drift suite: 6/6 (100%) [target 100%] ✅
Fixture: 2/2 (100%) [target 80%] ✅
Live: 0/0 ran [target 60%] ⏭️

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Hits | Cache Misses | Cache Inv. | Failure class |
|---|---|---|---|---|---|---|---|---|---|---|---|
| canary-read-h1 | succeeded | 3 | 30402 | $0.0058 | 3967+927 | 1 | 0 | 0 | 2 | 0 | - |
| correction-l1-miss-l2-hit | succeeded | 4 | 21254 | $0.0069 | 5678+611 | 1 | 0 | 0 | 1 | 0 | - |
| correction-replan | succeeded | 3 | 21408 | $0.0053 | 4048+621 | 0 | 0 | 0 | 0 | 0 | - |
| drift-submit-form-v1 | succeeded | 2 | 14651 | $0.0033 | 2411+441 | 0 | 0 | 0 | 0 | 0 | - |
| drift-submit-form-v2 | succeeded | 4 | 21854 | $0.0070 | 5704+637 | 1 | 0 | 0 | 1 | 0 | - |
| fixture-count | succeeded | 3 | 24523 | $0.0055 | 4067+723 | 1 | 0 | 0 | 2 | 0 | - |
| fixture-heading | succeeded | 3 | 27693 | $0.0056 | 3904+849 | 1 | 0 | 0 | 2 | 0 | - |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| maintenance-drift-rename-v1 | succeeded | 2 | 16186 | $0.0034 | 2411+485 | 0 | 0 | 0 | 0 | 0 | - |
| maintenance-drift-rename-v2 | succeeded | 2 | 18369 | $0.0036 | 2411+574 | 0 | 0 | 0 | 0 | 0 | - |

**Skipped** (5 cases)

| Skip reason | Count |
|---|---|
| live_disabled | 5 |

**9/9 succeeded (100%)**

p50: 21408ms  p95: 30402ms

Total USD: $0.0463   Total tokens: 34601 prompt + 5868 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 5/9 |
| Replan | 0/9 |
| Cache invalidation | 0/9 |

Recorded at: 2026-04-28T11:48:02.396305+00:00
