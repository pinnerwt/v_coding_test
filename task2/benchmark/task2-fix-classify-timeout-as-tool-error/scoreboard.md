Generated from eval run: 2026-04-28T07:38:48.532777+00:00

Drift suite: 1/6 (16%) [target 100%] ❌
Fixture: 1/2 (50%) [target 80%] ❌
Live: 0/0 ran [target 60%] ⏭️

**Failure histogram** (6 failed)

| Failure class | Count |
|---|---|
| no_done_emitted | 5 |
| tool_error | 1 |

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Hits | Cache Misses | Cache Inv. | Failure class |
|---|---|---|---|---|---|---|---|---|---|---|---|
| canary-read-h1 | succeeded | 3 | 30793 | $0.0053 | 3436+933 | 1 | 0 | 0 | 2 | 0 | - |
| correction-l1-miss-l2-hit | failed | 2 | 20680 | $0.0033 | 2008+640 | 0 | 0 | 0 | 0 | 0 | no_done_emitted |

<details><summary>step breakdown (2 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | read | 814 | 226 | 16070 |
| 2 | fail | 998 | 139 | 4610 |

</details>
| correction-replan | succeeded | 2 | 19388 | $0.0033 | 2052+604 | 0 | 0 | 0 | 0 | 0 | - |
| drift-submit-form-v1 | failed | 2 | 24292 | $0.0036 | 2020+768 | 0 | 0 | 0 | 0 | 0 | no_done_emitted |

<details><summary>step breakdown (2 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | read | 818 | 173 | 18811 |
| 2 | fail | 1004 | 167 | 5481 |

</details>
| drift-submit-form-v2 | failed | 2 | 23146 | $0.0035 | 2020+732 | 0 | 0 | 0 | 0 | 0 | no_done_emitted |

<details><summary>step breakdown (2 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | read | 818 | 173 | 17659 |
| 2 | fail | 1004 | 167 | 5487 |

</details>
| fixture-count | failed | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | tool_error |
| fixture-heading | succeeded | 3 | 26369 | $0.0050 | 3373+810 | 1 | 0 | 0 | 2 | 0 | - |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| maintenance-drift-rename-v1 | failed | 2 | 20082 | $0.0033 | 2011+629 | 0 | 0 | 0 | 0 | 0 | no_done_emitted |

<details><summary>step breakdown (2 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | read | 816 | 174 | 15042 |
| 2 | fail | 999 | 153 | 5040 |

</details>
| maintenance-drift-rename-v2 | failed | 2 | 19996 | $0.0033 | 2011+629 | 0 | 0 | 0 | 0 | 0 | no_done_emitted |

<details><summary>step breakdown (2 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | read | 816 | 174 | 14958 |
| 2 | fail | 999 | 153 | 5038 |

</details>

**Skipped** (5 cases)

| Skip reason | Count |
|---|---|
| live_disabled | 5 |

**3/9 succeeded (33%)**

p50: 20680ms  p95: 30793ms

Total USD: $0.0304   Total tokens: 18931 prompt + 5745 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 2/9 |
| Replan | 0/9 |
| Cache invalidation | 0/9 |

Recorded at: 2026-04-28T07:38:48.532777+00:00
