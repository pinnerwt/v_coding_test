Generated from eval run: 2026-04-28T20:41:30.410082+00:00

Drift suite: 6/6 (100%) [target 100%] ✅
Fixture: 2/2 (100%) [target 80%] ✅
Live: 0/0 ran [target 60%] ⏭️

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Hits | Cache Misses | Cache Inv. | Failure class |
|---|---|---|---|---|---|---|---|---|---|---|---|
| canary-read-h1 | succeeded | 1 | 6821 | $0.0015 | 1235+155 | 0 | 0 | 0 | 0 | 0 | - |
| correction-l1-miss-l2-hit | succeeded | 2 | 7884 | $0.0028 | 2450+184 | 1 | 0 | 0 | 1 | 0 | - |
| correction-replan | succeeded | 1 | 5117 | $0.0015 | 1209+132 | 0 | 0 | 0 | 0 | 0 | - |
| drift-submit-form-v1 | succeeded | 2 | 6330 | $0.0027 | 2411+142 | 0 | 0 | 0 | 0 | 0 | - |
| drift-submit-form-v2 | succeeded | 3 | 6465 | $0.0040 | 3768+133 | 1 | 0 | 0 | 1 | 0 | - |
| fixture-count | succeeded | 2 | 8021 | $0.0029 | 2562+193 | 0 | 0 | 0 | 0 | 0 | - |
| fixture-heading | succeeded | 1 | 5447 | $0.0015 | 1218+137 | 0 | 0 | 0 | 0 | 0 | - |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| maintenance-drift-rename-v1 | succeeded | 2 | 6067 | $0.0027 | 2411+140 | 0 | 0 | 0 | 0 | 0 | - |
| maintenance-drift-rename-v2 | succeeded | 2 | 5936 | $0.0027 | 2411+137 | 0 | 0 | 0 | 0 | 0 | - |

**Skipped** (5 cases)

| Skip reason | Count |
|---|---|
| live_disabled | 5 |

**9/9 succeeded (100%)**

p50: 6330ms  p95: 8021ms

Total USD: $0.0224   Total tokens: 19675 prompt + 1353 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 2/9 |
| Replan | 0/9 |
| Cache invalidation | 0/9 |

Recorded at: 2026-04-28T20:41:30.410082+00:00
