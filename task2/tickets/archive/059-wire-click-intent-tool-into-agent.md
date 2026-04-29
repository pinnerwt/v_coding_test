---
id: 59
slug: wire-click-intent-tool-into-agent
status: archived
tier: 5
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
archived_at: '2026-04-29'
trigger: surfaced from benchmark analysis on 2026-04-28 — every drift/correction failure
  shares the read→fail shape because the agent has no action verb. The plan.md design
  at line 38 always listed `click(intent)`; it was deferred during the initial loop.py
  scaffold and never landed.
---

59. **Wire `click(intent)` tool into `agent/loop.py`.** The current tool surface is `goto`, `read`, `done`, `fail` (`agent/loop.py:32`, `_TOOLS` list lines 40-121); there is no way for the agent to interact with the page beyond reading it. As a result, every benchmark case whose task starts with "Click the … button" — `correction-l1-miss-l2-hit`, `drift-submit-form-v1/v2`, `maintenance-drift-rename-v1/v2` — fails with the same shape: step 1 `read`, step 2 voluntary `fail`, `failure_class="no_done_emitted"`, zero escalations / replans. The locator pipeline at `agent/locate.py` (L1/L2/L3 + cache + AX fingerprint) and `_locate_via_ladder` at `loop.py:197` are already wired and used by `read`; this ticket reuses that ladder to add a `click` tool that calls `loc.click(timeout=…)` on the resolved Playwright Locator. Emit an `ActEvent` with `outcome ∈ {ok, no_effect, nav, timeout, error}` (the trace literal already exists at `agent/trace.py:69`). On `LocatorMiss`, surface to the supervisor for L1→L2 escalation (mechanism currently fires 3/9 from `read`-only escalation; clicks should add another path). Tests: (a) `_TOOLS` includes a `click` entry with `intent: str` parameter; (b) fixture-page test where the agent is given "Click the Submit button" reaches `done` in ≤ 4 steps against a stub LLM that emits `click(intent="Submit button")` then `done(...)`; (c) `outcome="nav"` recorded when the click triggers a same-tab navigation; (d) `LocatorMiss` from L1 triggers a `SupervisorEvent` with `next_tier="L2"` when reachable. *Why high-impact:* projected to flip 5 currently-red benchmark cases to green in a single change (44% → ~89% pass rate). *Trigger:* surfaced from benchmark analysis on 2026-04-28 — every drift/correction failure shares the read→fail shape because the agent has no action verb. The plan.md design at line 38 always listed `click(intent)`; it was deferred during the initial loop.py scaffold and never landed.
