## 1. Tests (Red)

- [x] 1.1 Add `test_goto_retries_once_on_transient_error` to `task2/tests/agent/test_browser.py`: stub `Page.goto` so the first call raises `PlaywrightError("net::ERR_NETWORK_CHANGED")` and the second returns normally; assert `Browser.goto` returns without raising and that `Page.goto` was called exactly twice
- [x] 1.2 Add `test_goto_does_not_retry_non_transient_error` to `task2/tests/agent/test_browser.py`: stub `Page.goto` to raise `PlaywrightError("net::ERR_NAME_NOT_RESOLVED")`; assert `Browser.goto` raises `NavigationError` and that `Page.goto` was called exactly once
- [x] 1.3 Run `uv run pytest task2/tests/agent/test_browser.py::test_goto_retries_once_on_transient_error task2/tests/agent/test_browser.py::test_goto_does_not_retry_non_transient_error` and confirm both fail (red bar)

## 2. Implementation (Green)

- [x] 2.1 In `task2/agent/browser.py`, add `import re` and `import time` at the top (if not already present)
- [x] 2.2 Define the transient-error pattern constant `_TRANSIENT_NAV_RE = re.compile(r"net::ERR_NETWORK_CHANGED|net::ERR_NETWORK_IO_SUSPENDED|net::ERR_INTERNET_DISCONNECTED|Page.goto.*Timeout")` at module level
- [x] 2.3 Modify `Browser.goto` to catch `PlaywrightError`, check the message against `_TRANSIENT_NAV_RE`; if matched, sleep 250 ms and retry the `Page.goto` call once; on second failure (or non-matching error), raise `NavigationError` as today
- [x] 2.4 Run `uv run pytest task2/tests/agent/test_browser.py` and confirm all tests pass (green bar)

## 3. Quality

- [ ] 3.1 Run `uv run ruff check task2/agent/browser.py task2/tests/agent/test_browser.py` and fix any lint issues
- [ ] 3.2 Run `uv run ruff format task2/agent/browser.py task2/tests/agent/test_browser.py` and confirm no changes needed
- [ ] 3.3 Run the full test suite `uv run pytest task2/tests/` and confirm no regressions
