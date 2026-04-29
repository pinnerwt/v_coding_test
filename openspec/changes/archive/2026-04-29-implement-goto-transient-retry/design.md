## Context

`Browser.goto` in `task2/agent/browser.py` wraps Playwright's synchronous `Page.goto`. Any `PlaywrightError` is immediately re-raised as a `NavigationError`. On 2026-04-28, `webvoyager-3` (GitHub `openai/gpt-2`) failed at step 0 with `net::ERR_NETWORK_CHANGED` — a known transient Chromium error caused by a network interface flap mid-navigation. The same case succeeded in two prior baselines. The error was infrastructure noise, not a real site failure, but it flipped the whole benchmark case red.

## Goals / Non-Goals

**Goals:**
- Retry `Browser.goto` exactly once after a matched transient Chromium error (250 ms sleep between attempts).
- Leave non-transient errors (e.g. `ERR_NAME_NOT_RESOLVED`, `ERR_CONNECTION_REFUSED`) unretried and immediately raised as `NavigationError`.
- Achieve this with zero new external dependencies and no changes to `NavigationError`'s public interface.
- Add unit tests covering both the retry path and the non-retry path, using a `Page` stub (no real Chromium).

**Non-Goals:**
- Multiple retries (ticket specifies exactly one).
- Retry on non-navigation methods (`read`, `screenshot`, `click_at`).
- Configurable retry count or delay via constructor or environment variable.
- Async support — the `Browser` class is fully synchronous.

## Decisions

### Decision: Regex match on error message text, not error subtype

Playwright's Python API raises `playwright.async_api.Error` (aliased as `PlaywrightError` in `browser.py`) for all navigation errors; there is no distinct subclass per Chromium net-error code. The only reliable discriminator is the error message string. The ticket supplies the exact regex: `r"net::ERR_NETWORK_CHANGED|net::ERR_NETWORK_IO_SUSPENDED|net::ERR_INTERNET_DISCONNECTED|Page.goto.*Timeout"`. This is already narrowly scoped to known-transient conditions, making false-positive retries unlikely.

Alternative considered: catch all `PlaywrightError` and always retry once. Rejected because it would silently retry non-transient failures (DNS, refused connections) that will never succeed, doubling latency for hard failures.

### Decision: `time.sleep(0.25)` between attempts

`Browser` is fully synchronous (no event loop). `asyncio.sleep` is not applicable. `time.sleep(0.25)` is the direct equivalent. The 250 ms delay is taken verbatim from the ticket.

### Decision: Retry logic lives in `Browser.goto`, not at the call site or a decorator

The retry is specific to transient Chromium navigation errors that only `goto` can observe. Placing it at the call site (agent loop, tool dispatch) would require every caller to duplicate the logic or would silently skip it for new callers. A decorator is unnecessary abstraction for a single method. Keeping it inside `goto` localises the change to one function and keeps the `NavigationError` contract unchanged.

### Decision: On second failure, raise the second exception (not the first)

The second attempt is the authoritative result when the first was transient. Raising the second exception ensures the error message reflects the actual final state (which may differ if network conditions changed) and is consistent with standard retry semantics. The first exception is attached as `__cause__` implicitly via `raise NavigationError(...) from e`.

## Risks / Trade-offs

- [Risk: False retry on a slow but non-transient load] The regex includes `Page.goto.*Timeout`, which matches a genuine timeout. A very slow but reachable page would be retried once, doubling the wait. Mitigation: Playwright's default navigation timeout (30 s) already makes this rare; one additional attempt is bounded cost.
- [Risk: Increased test complexity] The unit tests use a `Page` stub with a side-effect list. This is a well-established pattern in the existing test suite and does not require Playwright to be running.
- [Risk: Regex drift] If Playwright changes its error message format, the regex silently stops matching transient errors (falls back to no-retry, same as today). This is safe degradation.

## Migration Plan

1. Modify `Browser.goto` in `task2/agent/browser.py` to add the retry logic.
2. Add two unit tests to `task2/tests/agent/test_browser.py`.
3. Run `uv run pytest task2/tests/agent/test_browser.py` to confirm green.
4. Run `uv run ruff check task2/agent/browser.py task2/tests/agent/test_browser.py` to confirm clean.
5. No migration required — `NavigationError` public interface is unchanged; callers need no updates.

## Open Questions

(none — ticket is fully specified)
