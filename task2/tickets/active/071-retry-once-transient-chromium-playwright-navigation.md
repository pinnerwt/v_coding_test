---
id: 71
slug: retry-once-transient-chromium-playwright-navigation
status: active
tier: 1
urgency: P1
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence:
- task2/benchmark/task2-fix-qwen-http-400/webvoyager/20260428_233500.json
related: []
filed_pr: null
merged_pr: null
archived_at: null
trigger: user-flagged 2026-04-28 ("are we performing worse than before?") in `/done_pr`
  for `fix-qwen-http-400` after WebVoyager pass-rate dropped from 2/3 to 1/3 vs baseline.
  Cross-run check shows this case has otherwise been stable.
---

71. **Retry once on transient Chromium/Playwright navigation errors before recording WebVoyager failure.** `webvoyager-3` (GitHub `openai/gpt-2`) failed at step 0 with `failure_class="tool_error"` and `failure_detail="NavigationError('failed to navigate to https://github.com/openai/gpt-2: Page.goto: net::ERR_NETWORK_CHANGED ...')"` in `task2/benchmark/task2-fix-qwen-http-400/webvoyager/20260428_233500.json`. The same case succeeded with `steps=6, $0.0405` in baseline `task2-benchmarks-readme-and-tier0/webvoyager/baseline.json` and `steps=5, $0.0299` in `task2-implement-webvoyager-tier1`. `net::ERR_NETWORK_CHANGED` is a known transient Chromium error (typically caused by a network interface flap mid-navigation) — a single retry would almost certainly recover. Concrete fix: in `agent/browser.py:Browser.goto` (or wherever `Page.goto` is wrapped), catch `playwright.async_api.Error` whose message matches the regex `r"net::ERR_NETWORK_CHANGED|net::ERR_NETWORK_IO_SUSPENDED|net::ERR_INTERNET_DISCONNECTED|Page.goto.*Timeout"`, sleep 250ms, and retry once. If the retry also fails, raise as today. Tests: a unit test in `task2/tests/test_browser.py` injects a `Page` stub whose first `goto` call raises a fake `ERR_NETWORK_CHANGED` and the second returns normally, asserts `Browser.goto` returns success and only one error was raised externally; a second test asserts a non-transient error (e.g. `ERR_NAME_NOT_RESOLVED`) is NOT retried. *Why useful:* `webvoyager-3` regressed pass-rate from 2/3 to 1/3 on the 2026-04-28 run for branch `task2/fix-qwen-http-400` purely on a transient Chromium flake. A bounded one-shot retry caps the cost (≤ 250ms + one extra goto on rare transients) while preventing a whole case from flipping red. *Trigger:* user-flagged 2026-04-28 ("are we performing worse than before?") in `/done_pr` for `fix-qwen-http-400` after WebVoyager pass-rate dropped from 2/3 to 1/3 vs baseline. Cross-run check shows this case has otherwise been stable.
