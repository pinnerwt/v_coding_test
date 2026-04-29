## Why

`task2/agent/browser.py::Browser.goto` currently waits for the `load` lifecycle event (all subresources — images, fonts, lazy scripts) before returning. On content-heavy pages like Wikipedia article views, this routinely blocks 15-30s per goto while the agent only needs the DOM and AX-tree to operate. WebVoyager-1 (Wikipedia Turing-Award-2018 task) has timed out at 20 steps in every run for the last 8 benchmarks, with second-half steps averaging ~28s/step vs ~7s/step in the first half — a 4× slowdown traced directly to `wait_until="load"` stalling on Wikipedia's asset graph. Cost per benchmark: ~$0.30 / ~310K prompt tokens / ~6 minutes wallclock for that single case alone.

## What Changes

- `task2/agent/browser.py::Browser.goto` — change both `self._page.goto(url, wait_until="load")` calls (lines 83 and 89) to `self._page.goto(url, wait_until="domcontentloaded", timeout=15000)`. The 15s timeout is a hard ceiling tighter than Playwright's 30s default.
- `task2/tests/agent/test_browser_goto_domcontentloaded.py` — new file with 3 deterministic tests against a per-test `http.server` that holds a subresource open or stalls the HTML response.
- `task2/tests/agent/test_browser.py` — update three existing patched-goto tests' `fake_goto` signature to absorb the new `timeout` kwarg (signature plumbing only; no behavior change to retry logic).
- No new tools, no new agent loop changes, no new CLI flags.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `browser-tool`: `Browser.goto(url)` now waits for `domcontentloaded` (DOM ready) instead of `load` (all subresources), and bounds the wait at 15s instead of Playwright's 30s default. The transient-retry behavior is unchanged.

## Impact

- `task2/agent/browser.py`: per-step latency on subresource-heavy pages drops substantially; existing fast pages are unaffected (their DCL ≈ load timing).
- `task2/tests/agent/test_browser.py`: three existing test signatures updated; behavior unchanged.
- WebVoyager-1: expected ≥40% reduction in `latency_ms_total` on a re-run (≤220s / ≤$0.20 vs current ~370s / ~$0.30). Pass-rate impact for webvoyager-1 is 0 (this is a planner / context-budget problem, not browser-speed).
- No new dependencies.
