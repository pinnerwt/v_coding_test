## Why

`webvoyager-3` (GitHub `openai/gpt-2`) failed at step 0 on the 2026-04-28 run for branch `task2/fix-qwen-http-400` with `NavigationError('failed to navigate to https://github.com/openai/gpt-2: Page.goto: net::ERR_NETWORK_CHANGED ...')`. The same case succeeded in two prior baselines, confirming this is a transient Chromium network flap, not a real site failure. A single bounded retry recovers the case with negligible cost (≤ 250 ms + one extra goto on rare transients) and prevents a whole benchmark case from flipping red on an infrastructure fluke.

## What Changes

- `Browser.goto` in `task2/agent/browser.py` is updated to catch `playwright.async_api.Error` whose message matches the regex `net::ERR_NETWORK_CHANGED|net::ERR_NETWORK_IO_SUSPENDED|net::ERR_INTERNET_DISCONNECTED|Page.goto.*Timeout`, sleep 250 ms, and retry the navigation once before propagating failure.
- Non-transient errors (e.g. `ERR_NAME_NOT_RESOLVED`, `ERR_CONNECTION_REFUSED`) are not retried and raise `NavigationError` immediately as today.
- Two new unit tests are added to `task2/tests/agent/test_browser.py` using `Page` stubs — one covering the transient-error retry path (first call raises `ERR_NETWORK_CHANGED`, second succeeds), one asserting a non-transient error is never retried.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `browser-tool`: The `goto(url)` requirement gains a transient-retry sub-behavior — on a matched transient Chromium error the method sleeps 250 ms and retries once before raising `NavigationError`.

## Impact

- `task2/agent/browser.py`: `Browser.goto` modified.
- `task2/tests/agent/test_browser.py`: two new unit tests added.
- No API surface changes; `NavigationError` is still the only externally visible exception from `goto`.
- No new dependencies; `asyncio.sleep` is not applicable (sync API) — uses `time.sleep`.
