---
id: 87
slug: bypass-page-title-implicit-wait-via-evaluate
status: active
tier: 5
urgency: P2
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 25
dependencies: []
pre_flight_gates: []
evidence:
- task2/agent/observe.py
- task2/benchmark/task2-fix-goto-domcontentloaded/webvoyager/20260429_122531.json
related:
- 86
filed_pr: null
merged_pr: null
archived_at: null
trigger: 'deep-dive analysis of PR #133 / ticket #85 on 2026-04-29 — `page.title()` runs every step inside `build_observation`, waits on Playwright''s default page-lifecycle timeout, and contributes to the 28-30s plateau on hydrating Wikipedia article pages.'
---

87. **Replace `page.title()` with `page.evaluate("() => document.title")` in `build_observation` to remove a per-step lifecycle-bound wait.** `agent/observe.py:114` calls `page.title()` once per step. Playwright's `Page.title()` is documented to wait for the main frame to be in a "ready" state and respects the context's default timeout (30s by default; 5s after ticket #86 lands). On hydrating pages with continuously-running scripts, that wait can be the entire reason a step blocks — independent of `goto`'s `wait_until` and independent of locator timeouts on `read`/`click`. Replacing it with a direct JS evaluation reads the title synchronously against the JS engine without participating in Playwright's lifecycle waiting machinery. **Concrete fix:** in `agent/observe.py:build_observation`, change `"title": page.title(),` to `"title": page.evaluate("() => document.title")`. `page.evaluate` returns whatever the JS expression evaluates to right now; `document.title` is a string that's defined as soon as the `<title>` element exists (which is part of DOMContentLoaded, already guaranteed by ticket #85). **Acceptance:** new test `task2/tests/agent/test_observe_title_via_evaluate.py` builds a `Browser` against a fixture page whose `<title>` is `Hello`, then patches `b._page.title` to `lambda *a, **kw: time.sleep(10)` (would block 10s if called) — asserts `build_observation(b, [])` returns within 1 second AND `result["title"] == "Hello"`. Existing observation tests pass unchanged. **Risks:** (a) `page.evaluate` itself can raise if the page is navigating mid-call; wrap in `try/except PlaywrightError` and fall back to empty string. (b) if the page is a frameset / cross-origin embed, `document.title` may be the parent's title rather than the active frame's; for WebVoyager's seed (Wikipedia, arXiv, GitHub) this is not a concern. *Why useful:* tactical companion to ticket #86 — even with the context default timeout lowered to 5s, every step still incurs that 5s wait if the page is genuinely mid-hydration. `evaluate` bypasses the wait entirely. Estimated impact: shaves 1-3 seconds off every step in the slow region (8 steps × 2s ≈ 16s on webvoyager-1, ~3% suite latency). pass_rate=0 (no convergence change), tokens_pct=0, latency_pct=25 (additive on top of #86). Lower urgency than #86 because the savings are smaller and the lifecycle issue largely goes away once #86 caps the default timeout. *Trigger:* PR #133 deep-dive on 2026-04-29 — `page.title()` identified as one of three Playwright-default-timeout call sites contributing to the 28-30s second-half-step plateau.
