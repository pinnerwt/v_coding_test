Generated from eval run: 2026-04-28T07:16:33.061248+00:00

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
| canary-read-h1 | succeeded | 3 | 27810 | $0.0052 | 3436+863 | 1 | 0 | 0 | 2 | 0 | - |
| correction-l1-miss-l2-hit | failed | 2 | 23570 | $0.0035 | 2008+737 | 0 | 0 | 0 | 0 | 0 | no_done_emitted |

<details><summary>step breakdown (2 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | read | 814 | 226 | 19001 |
| 2 | fail | 998 | 137 | 4569 |

</details>
| correction-replan | succeeded | 2 | 19413 | $0.0033 | 2052+604 | 0 | 0 | 0 | 0 | 0 | - |
| drift-submit-form-v1 | failed | 2 | 26739 | $0.0037 | 2020+848 | 0 | 0 | 0 | 0 | 0 | no_done_emitted |

<details><summary>step breakdown (2 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | read | 818 | 197 | 21254 |
| 2 | fail | 1004 | 167 | 5485 |

</details>
| drift-submit-form-v2 | failed | 2 | 26482 | $0.0037 | 2020+843 | 0 | 0 | 0 | 0 | 0 | no_done_emitted |

<details><summary>step breakdown (2 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | read | 818 | 197 | 20995 |
| 2 | fail | 1004 | 167 | 5487 |

</details>
| fixture-count | failed | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | tool_error |
| fixture-heading | succeeded | 3 | 26340 | $0.0050 | 3373+809 | 1 | 0 | 0 | 2 | 0 | - |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |
| maintenance-drift-rename-v1 | failed | 2 | 20567 | $0.0033 | 2011+637 | 0 | 0 | 0 | 0 | 0 | no_done_emitted |

<details><summary>step breakdown (2 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | read | 816 | 174 | 15279 |
| 2 | fail | 999 | 161 | 5288 |

</details>
| maintenance-drift-rename-v2 | failed | 2 | 20231 | $0.0033 | 2011+637 | 0 | 0 | 0 | 0 | 0 | no_done_emitted |

<details><summary>step breakdown (2 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | read | 816 | 174 | 14945 |
| 2 | fail | 999 | 161 | 5286 |

</details>

**Skipped** (5 cases)

| Skip reason | Count |
|---|---|
| live_disabled | 5 |

**3/9 succeeded (33%)**

p50: 23570ms  p95: 27810ms

Total USD: $0.0309   Total tokens: 18931 prompt + 5978 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 2/9 |
| Replan | 0/9 |
| Cache invalidation | 0/9 |

Recorded at: 2026-04-28T07:16:33.061248+00:00
