## 1. Red — failing tests

- [x] 1.1 Create `task2/tests/agent/test_browser_goto_domcontentloaded.py` with a per-test `http.server` handler factory mirroring `task2/tests/conftest.py:20-42` (daemon thread, shutdown on teardown).
- [x] 1.2 Add `test_goto_returns_after_domcontentloaded_when_subresource_hangs` — handler serves `index.html` with `<img src="/slow.png">` and blocks `GET /slow.png` for 8s before responding 200. Assert `Browser.goto` returns within 3 seconds (using `time.monotonic()` deltas).
- [x] 1.3 Add `test_goto_raises_navigation_error_on_dcl_timeout` — handler holds the HTML response for 20 seconds. Assert `Browser.goto` raises `NavigationError` within ≤31 seconds (15s timeout + transient-retry slack).
- [x] 1.4 Add `test_goto_passes_wait_until_domcontentloaded_arg` — patch `b._page.goto` to capture kwargs; assert `kwargs["wait_until"] == "domcontentloaded"` and `kwargs["timeout"] == 15000`.
- [x] 1.5 Update `task2/tests/agent/test_browser.py:148-187` — change `fake_goto(url, wait_until)` signature in `test_goto_retries_once_on_transient_error`, `test_goto_does_not_retry_non_transient_error`, `test_goto_raises_navigation_error_on_second_transient_failure` to `fake_goto(url, **kwargs)` so they accept the new `timeout` kwarg.
- [x] 1.6 Run `cd task2 && uv run pytest tests/agent/test_browser_goto_domcontentloaded.py tests/agent/test_browser.py -x` — confirm new tests fail (current code passes `wait_until="load"`, no `timeout` kwarg) and the three updated patched-goto tests fail because their signatures don't accept the new kwarg yet (until step 2.1 updates the prod code).

## 2. Green — minimal implementation

- [x] 2.1 In `task2/agent/browser.py::Browser.goto`, change both `self._page.goto(url, wait_until="load")` calls (lines 83 and 89) to `self._page.goto(url, wait_until="domcontentloaded", timeout=15000)`.
- [x] 2.2 Run `cd task2 && uv run pytest tests/agent/test_browser_goto_domcontentloaded.py tests/agent/test_browser.py -x` — all tests pass.

## 3. Full suite

- [x] 3.1 Run `cd task2 && uv run pytest` — confirm no regressions in the broader test suite.

## 4. Clean — lint and format

- [x] 4.1 `cd task2 && uv run ruff check --fix .`.
- [x] 4.2 `cd task2 && uv run ruff format .`.
- [x] 4.3 `cd task2 && uv run ruff check .` — confirm zero errors, zero warnings.
- [x] 4.4 `cd task2 && uv run pytest` — green bar after formatting.
