Generated from eval run: 2026-04-28T05:45:26.001103+00:00

Drift suite: 1/6 (16%) [target 100%] ❌
Fixture: 1/2 (50%) [target 80%] ❌
Live: 0/0 ran [target 60%] ⏭️

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Inv. | Failure class |
|---|---|---|---|---|---|---|---|---|---|
| canary-read-h1 | succeeded | 3 | 26060 | $0.0050 | 3436+790 | 1 | 0 | 0 | - |
| correction-l1-miss-l2-hit | failed | 2 | 21569 | $0.0033 | 2008+638 | 0 | 0 | 0 | no_done_emitted |

<details><summary>step breakdown (2 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | read | 814 | 226 | 16859 |
| 2 | fail | 998 | 137 | 4710 |

</details>
| correction-replan | succeeded | 2 | 19932 | $0.0033 | 2052+601 | 0 | 0 | 0 | - |
| drift-submit-form-v1 | failed | 2 | 26997 | $0.0037 | 2020+824 | 0 | 0 | 0 | no_done_emitted |

<details><summary>step breakdown (2 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | read | 818 | 173 | 21337 |
| 2 | fail | 1004 | 167 | 5660 |

</details>
| drift-submit-form-v2 | failed | 2 | 26525 | $0.0037 | 2020+819 | 0 | 0 | 0 | no_done_emitted |

<details><summary>step breakdown (2 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | read | 818 | 173 | 20850 |
| 2 | fail | 1004 | 167 | 5675 |

</details>
| fixture-count | failed | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | tool_error |
| fixture-heading | succeeded | 3 | 27211 | $0.0050 | 3373+810 | 1 | 0 | 0 | - |
| live-conditional-pick | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-form-fill | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-multi-page-nav | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-read-summarize | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| live-search-extract | skipped | 0 | 0 | $0.0000 | 0+0 | 0 | 0 | 0 | - |
| maintenance-drift-rename-v1 | failed | 2 | 20309 | $0.0032 | 2011+615 | 0 | 0 | 0 | no_done_emitted |

<details><summary>step breakdown (2 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | read | 816 | 175 | 15569 |
| 2 | fail | 999 | 138 | 4740 |

</details>
| maintenance-drift-rename-v2 | failed | 2 | 20199 | $0.0032 | 2011+615 | 0 | 0 | 0 | no_done_emitted |

<details><summary>step breakdown (2 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | read | 816 | 175 | 15456 |
| 2 | fail | 999 | 138 | 4743 |

</details>

**Skipped** (5 cases)

| Skip reason | Count |
|---|---|
| live_disabled | 5 |

**3/9 succeeded (33%)**

p50: 21569ms  p95: 27211ms

Total USD: $0.0304   Total tokens: 18931 prompt + 5712 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 2/9 |
| Replan | 0/9 |
| Cache invalidation | 0/9 |

Recorded at: 2026-04-28T05:45:26.001103+00:00
