Generated from eval run: 2026-04-26T03:27:29+00:00

Drift suite: 0/0 ran [target 100%] ⏭️
Fixture: 1/2 (50%) [target 80%] ❌
Live: 0/0 ran [target 60%] ⏭️

| Case | Status | Steps | Latency (ms) | USD | Tokens (P+C) | Escalations | Replans | Cache Hits | Cache Misses | Cache Inv. | Failure class |
|---|---|---|---|---|---|---|---|---|---|---|---|
| fixture-heading | succeeded | 2 | 400 | $0.0005 | 200+30 | 0 | 0 | 0 | 0 | 0 | - |
| fixture-count | failed | 1 | 800 | $0.0000 | 0+0 | 0 | 0 | 0 | 0 | 0 | - |

<details><summary>step breakdown (1 steps)</summary>

| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |
|---|---|---|---|---|
| 1 | fail | 0 | 0 | 800 |

</details>

**1/2 succeeded (50%)**

p50: 400ms  p95: 800ms

Total USD: $0.0005   Total tokens: 200 prompt + 30 completion

| Tier | Count |
|---|---|
| (none) | 0 |

**Mechanism firing rates**

| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | 0/2 |
| Replan | 0/2 |
| Cache invalidation | 0/2 |

Recorded at: 2026-04-26T03:27:29+00:00
