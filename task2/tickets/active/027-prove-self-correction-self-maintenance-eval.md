---
id: 27
slug: prove-self-correction-self-maintenance-eval
status: active
tier: 2
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related: []
filed_pr: null
merged_pr: null
archived_at: null
trigger: ''
---

27. **Prove self-correction and self-maintenance in the eval, not just in code** — the mechanisms exist (escalation ladder L1→L2→L4 in `agent/locate.py:466-487`, supervisor halt → one-shot replan in `agent/loop.py:414-426`, AX-fingerprint cache invalidation in `agent/locate.py:454-463` + `agent/locator_cache.py:166-170`) but the eval never asserts they fire — `tests/test_eval.py:286-339` only checks case count and result shape on the drift variants, and no test exercises the supervisor-halt → replan path or the cache-invalidation path end-to-end. Close this gap so the brief's headline criterion ("substance of the self-correction / self-maintenance mechanisms (not just try/except retries)") is demonstrable to a reviewer. Concretely: (a) extend `CaseResult` (per ticket 20) with `escalations: [{intent, from_tier, to_tier, reason}]`, `replans: int`, and `cache_events: {hits, invalidations, misses}`, populated by reading `LocateEvent` / `SupervisorEvent` / `PlanEvent` rows from the trace — no new instrumentation, just aggregation. (b) Author at least three new fixture cases under `eval/cases/` whose only success path requires the mechanisms: `correction-l1-miss-l2-hit.yaml` (target has no accessible name → must fall to L2), `correction-replan.yaml` (initial plan goes to a dead-end page → halt must trigger replan from current state), `maintenance-drift-rename.yaml` (drift v1 then re-run as v2 in the same process so the cache is warm on v1 and *must* invalidate on v2). (c) Add assertions in `tests/test_eval.py` that for each of those cases the corresponding `CaseResult` field is non-zero (e.g. drift case: `cache_events.invalidations >= 1` *and* status `succeeded`; replan case: `replans == 1` *and* status `succeeded`; escalation case: `escalations` contains an entry with `from_tier="L1_ax"` and `to_tier="L2_dom"`). (d) Update `scripts/score.py` to surface per-case escalation/replan/cache columns and overall mechanism-firing rates in the scoreboard markdown. (e) Add a top-level "Self-correction & self-maintenance — measured" subsection in `task2/README.md` that links to the latest scoreboard and names the three diagnostic cases. Done bar: the three new cases pass; the assertions above are real (removing the mechanism in code makes them fail — verify by temporarily forcing `policy="halt"` to skip replan and watching `correction-replan.yaml` go red); the scoreboard shows non-zero values in the new columns; honest gaps (no transient-failure retry, no post-action assertion, single replan budget, coarse fingerprint, vision tier uncached) are listed in the README subsection.
