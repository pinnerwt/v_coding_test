Generated from eval run: 2026-04-28T09:23:46.473363+00:00

Drift suite: 1/6 (16%) [target 100%] ❌
Fixture: 2/2 (100%) [target 80%] ✅
Live: 0/0 ran [target 60%] ⏭️

**Failure histogram** (5 failed)

| Failure class | Count |
|---|---|
| no_done_emitted | 5 |

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Hits | Cache Misses | Cache Inv. | Failure class |
|---|---|---|---|---|---|---|---|---|---|---|---|
| canary-read-h1 | succeeded | 3 | 28487 | $0.0052 | 3436+882 | 1 | 0 | 0 | 2 | 0 | - |
| correction-l1-miss-l2-hit | failed | 2 | 16550 | $0.0030 | 2008+512 | 0 | 0 | 0 | 0 | 0 | no_done_emitted |

<details><summary>step breakdown (2 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | read | 814 | 99 | 11961 |
| 2 | fail | 998 | 138 | 4589 |

</details>
| correction-replan | succeeded | 2 | 19117 | $0.0032 | 2052+594 | 0 | 0 | 0 | 0 | 0 | - |
| drift-submit-form-v1 | failed | 2 | 19785 | $0.0033 | 2020+618 | 0 | 0 | 0 | 0 | 0 | no_done_emitted |

<details><summary>step breakdown (2 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | read | 818 | 198 | 14674 |
| 2 | fail | 1004 | 155 | 5111 |

</details>
| drift-submit-form-v2 | failed | 2 | 19699 | $0.0033 | 2020+618 | 0 | 0 | 0 | 0 | 0 | no_done_emitted |

<details><summary>step breakdown (2 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | read | 818 | 198 | 14585 |
| 2 | fail | 1004 | 155 | 5114 |

</details>
| fixture-count | succeeded | 3 | 21876 | $0.0048 | 3528+657 | 1 | 0 | 0 | 2 | 0 | - |
| fixture-heading | succeeded | 3 | 23511 | $0.0048 | 3373+727 | 1 | 0 | 0 | 2 | 0 | - |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| maintenance-drift-rename-v1 | failed | 2 | 22218 | $0.0034 | 2011+693 | 0 | 0 | 0 | 0 | 0 | no_done_emitted |

<details><summary>step breakdown (2 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | read | 816 | 174 | 17418 |
| 2 | fail | 999 | 145 | 4800 |

</details>
| maintenance-drift-rename-v2 | failed | 2 | 22041 | $0.0034 | 2011+693 | 0 | 0 | 0 | 0 | 0 | no_done_emitted |

<details><summary>step breakdown (2 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | read | 816 | 174 | 17238 |
| 2 | fail | 999 | 145 | 4803 |

</details>

**Skipped** (5 cases)

| Skip reason | Count |
|---|---|
| live_disabled | 5 |

**4/9 succeeded (44%)**

p50: 21876ms  p95: 28487ms

Total USD: $0.0344   Total tokens: 22459 prompt + 5994 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 3/9 |
| Replan | 0/9 |
| Cache invalidation | 0/9 |

Recorded at: 2026-04-28T09:23:46.473363+00:00
