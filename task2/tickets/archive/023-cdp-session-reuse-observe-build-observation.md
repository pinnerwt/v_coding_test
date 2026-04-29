---
id: 23
slug: cdp-session-reuse-observe-build-observation
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
trigger: CDP session reuse in `observe.build_observation`
---

23. **CDP session reuse in `observe.build_observation`** — `_ax_nodes` currently calls `page.context.new_cdp_session(page)` and `cdp.detach()` on every `build_observation` call (every agent step). Attach once per page lifetime (e.g. lazily on first observation, cached on the `Browser` instance keyed by page id) and reuse across steps; detach on `Browser.__exit__` / page close. Tests: with a single browser session and N=10 `build_observation` calls, only one CDP session is opened (assert via spy on `page.context.new_cdp_session`); navigating to a new page invalidates the cached session and a fresh one is opened on the next call; `Browser.__exit__` detaches without raising; existing observe tests still pass unchanged.
