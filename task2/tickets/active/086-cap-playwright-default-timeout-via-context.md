---
id: 86
slug: cap-playwright-default-timeout-via-context
status: active
tier: 5
urgency: P1
axes:
  pass_rate: 0
  tokens_pct: 30
  latency_pct: 60
dependencies: []
pre_flight_gates: []
evidence:
- task2/agent/browser.py
- task2/agent/observe.py
- task2/benchmark/task2-fix-goto-domcontentloaded/webvoyager/20260429_122531.json
- task2/benchmark/task2-implement-fast-path-ticket-archival/webvoyager/20260429_104152.json
related:
- 85
- 87
filed_pr: null
merged_pr: null
archived_at: null
trigger: 'deep-dive analysis of PR #133 / ticket #85 on 2026-04-29 — the goto-DCL fix only moved suite latency -6.8% because the dominant late-stage cost is post-goto `read`/`click`/`page.title()` operations whose implicit Playwright waits inherit the default 30000 ms timeout. webvoyager-1 step 13 (read) = 29271ms vs step 11 (read at similar prompt size) = 5610ms confirms the bottleneck is page-state-dependent, not LLM-bound.'
---

86. **Lower Playwright's context-level default timeout so post-goto `read`/`click` operations stop sitting on the 30s Playwright default.** Ticket #85 capped `Browser.goto` at `timeout=15000` but every other Playwright API call in the agent (`page.title()` in `agent/observe.py:114`, `page.locator(...).count()` and `locator.first.text_content()` in `agent/browser.py:96-99`, the click actionability path in `Browser.click_at`) inherits the **default 30000 ms** timeout. On Wikipedia-style pages where the DOM is mid-hydration, every one of these can stall up to 30s. Per-step trace from PR #133's WebVoyager run shows steps 13/14/15/16/17/19/20 sitting at 28-31s each — and those are reads/clicks, not gotos. **Concrete fix:** in `Browser.__enter__`, after `self._context = self._browser.new_context()`, call `self._context.set_default_timeout(5000)` and `self._context.set_default_navigation_timeout(15000)`. The navigation timeout stays at 15s to match `goto`'s explicit `timeout=15000` (consistency: a default-timeout fallback path should match the explicit one). The 5s default for non-navigation operations is empirically grounded: step 11's read at 20.5K prompt tokens completed in 5610ms (LLM ≈ 5s, locator ≈ 0.5s), so 5s is the right ceiling for "this DOM operation has had a fair chance to settle and isn't going to." **Acceptance:** new test `task2/tests/agent/test_browser_default_timeouts.py` patches `playwright_chromium`'s `new_context` to record the timeout calls and asserts both `set_default_timeout(5000)` and `set_default_navigation_timeout(15000)` were called exactly once after context creation; an integration test serves an HTML body with a `<body>` element whose JS continuously mutates the DOM (simulating a hydrating page) and asserts `Browser.read("body")` returns within 6 seconds (the 5s timeout fires and the locator yields the current body text — `text_content` returns synchronously once the locator resolves). All existing browser tests pass unchanged because they hit fast fixture pages whose locator operations resolve in <100ms. The next WebVoyager run on a branch landing this fix should show webvoyager-1 second-half steps drop from ~30s/step to ≤8s/step (LLM prefill at 22K tokens ≈ 5-7s + locator ≤ 1s), giving a target suite latency reduction ≥30% vs the PR #133 baseline of 488615ms total. **Risks:** (a) some legitimately slow pages may now fail with `TimeoutError` where they previously succeeded after 20-25s; mitigation: catch `PlaywrightTimeoutError` in `Browser.read` and convert to `ElementNotFound` with a message naming the timeout, so the agent can replan rather than crashing the run. (b) if `read("body")` partially returns truncated text on timeout, downstream extraction may produce wrong evidence; verify `text_content()` semantics under timeout — the Playwright doc says it raises rather than returning partial. (c) interaction with the existing `_TRANSIENT_NAV_RE` retry: after this fix, `goto` timeouts still retry once (matching `Page.goto.*Timeout`); a worst-case `goto` is still ~30s wallclock (15s × 2 + 250ms). That's expected and outside this ticket's scope. *Why useful:* this is the highest-leverage latency fix for webvoyager-1 because the dominant cost is no longer the goto itself (#85 fixed that) but every subsequent locator operation. Per-step latency at 22K prompt tokens is currently ~30s; the LLM call alone explains only ~5-8s of that (step 11 control), leaving ~22-25s of Playwright-side wait. Capping the default timeout at 5s collapses that 22-25s to ≤5s per step. With 8 slow steps in the 20-step trace, that's a ~150-180s improvement on webvoyager-1 alone (~30% of suite total). pass_rate=0 because the agent will still hit the step ceiling (that's #72's job), but tokens_pct=30 (fewer wasted token cycles per step) and latency_pct=60 (the dominant fix). *Trigger:* PR #133 deep-dive on 2026-04-29 — the goto-DCL fix shipped but the suite latency moved only -6.8% because Playwright's default timeout governs every other call site.
