Generated from eval run: 2026-04-28T05:04:23.392225+00:00

Drift suite: 1/6 (16%) [target 100%] ❌
Fixture: 1/2 (50%) [target 80%] ❌
Live: 0/0 ran [target 60%] ⏭️

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Inv. | Failure class |
|---|---|---|---|---|---|---|---|---|---|
| canary-read-h1 | succeeded | 3 | 26041 | $0.0050 | 3436+781 | 1 | 0 | 0 | - |
| correction-l1-miss-l2-hit | failed | 2 | 24303 | $0.0035 | 2008+739 | 0 | 0 | 0 | no_done_emitted |
| correction-replan | succeeded | 2 | 19904 | $0.0033 | 2052+602 | 0 | 0 | 0 | - |
| drift-submit-form-v1 | failed | 2 | 27147 | $0.0037 | 2020+836 | 0 | 0 | 0 | no_done_emitted |
| drift-submit-form-v2 | failed | 2 | 26810 | $0.0037 | 2020+828 | 0 | 0 | 0 | no_done_emitted |
| fixture-count | failed | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | tool_error |
| fixture-heading | succeeded | 3 | 27116 | $0.0050 | 3373+810 | 1 | 0 | 0 | - |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| maintenance-drift-rename-v1 | failed | 2 | 23442 | $0.0034 | 2011+717 | 0 | 0 | 0 | no_done_emitted |
| maintenance-drift-rename-v2 | failed | 2 | 22886 | $0.0034 | 2011+703 | 0 | 0 | 0 | no_done_emitted |

**Skipped** (5 cases)

| Skip reason | Count |
|---|---|
| live_disabled | 5 |

**3/9 succeeded (33%)**

p50: 24303ms  p95: 27147ms

Total USD: $0.0310   Total tokens: 18931 prompt + 6016 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 2/9 |
| Replan | 0/9 |
| Cache invalidation | 0/9 |

Recorded at: 2026-04-28T05:04:23.392225+00:00
