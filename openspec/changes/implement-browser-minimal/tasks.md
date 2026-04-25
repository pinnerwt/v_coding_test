## 1. Dependency setup

- [x] 1.1 Add `playwright` as a runtime dep via `uv add playwright` (run in `task2/`); commit the resulting `pyproject.toml` + `uv.lock`.
- [x] 1.2 Run `uv run playwright install chromium` locally; document the step in `task2/README.md` (create the file if it does not exist; keep the README minimal — setup + how to run tests).

## 2. Test fixtures (red)

- [x] 2.1 Create `task2/tests/fixtures/index.html` with at least an `<h1>Hello, world</h1>` and a paragraph element used by the multi-match scenario (`<p>first</p><p>second</p>`).
- [x] 2.2 Create `task2/tests/fixtures/whitespace.html` with `<h1>\n  Hello\n</h1>` for the whitespace-strip scenario.
- [x] 2.3 Add `task2/tests/conftest.py` with a session-scoped `fixture_server` pytest fixture that spins up `http.server.ThreadingHTTPServer` on `("127.0.0.1", 0)` serving `task2/tests/fixtures/`, yields the base URL, and shuts the server down on teardown.
- [x] 2.4 Add a session-scoped `playwright_chromium` fixture in `conftest.py` that starts `sync_playwright()`, launches headless Chromium once, and stops both on teardown.

## 3. Failing tests (red)

- [x] 3.1 Add `task2/tests/test_browser.py` with `test_goto_and_read_h1` exercising the happy-path scenario from the spec; instantiate `Browser` against the session-scoped Chromium so each test gets a fresh context+page.
- [x] 3.2 Add `test_read_strips_whitespace` against `whitespace.html`.
- [x] 3.3 Add `test_read_returns_first_match_for_multiple` against `index.html`.
- [x] 3.4 Add `test_read_raises_element_not_found` asserting `ElementNotFound` includes the selector in its message.
- [x] 3.5 Add `test_goto_raises_navigation_error` pointing at a closed port (e.g. `http://127.0.0.1:1/...`).
- [x] 3.6 Add `test_context_manager_cleans_up_on_exception` that raises inside the `with` block and asserts the original exception propagates.
- [x] 3.7 Add `test_calls_after_close_raise_browser_closed` to enforce the post-`__exit__` contract.
- [x] 3.8 Add `test_exception_hierarchy` importing `BrowserError`, `NavigationError`, `ElementNotFound`, `BrowserClosed` and asserting subclass relationships.
- [x] 3.9 Run `uv run pytest task2/tests/test_browser.py -x` and confirm every test fails for the expected reason (missing module / missing methods), not for setup errors.

## 4. Implementation (green)

- [x] 4.1 Create `task2/agent/browser.py` defining `BrowserError`, `NavigationError`, `ElementNotFound`, `BrowserClosed`.
- [x] 4.2 Implement `Browser.__init__` supporting two modes: zero-arg (own the Playwright runtime + Chromium launch) and an injected `playwright_browser` (used by tests to share a session-scoped Chromium). Both modes create a fresh `BrowserContext` and `Page`.
- [x] 4.3 Implement `__enter__`/`__exit__` to stop only what this instance owns; mark the instance closed and ensure subsequent `goto`/`read` calls raise `BrowserClosed`.
- [x] 4.4 Implement `goto(url)` waiting for the `load` lifecycle event; wrap Playwright's `Error` into `NavigationError` with the URL in the message.
- [x] 4.5 Implement `read(selector)` using `page.locator(selector).first.text_content()` (or equivalent), `.strip()` the result, raise `ElementNotFound(selector)` when count is zero.
- [x] 4.6 Run `uv run pytest task2/tests/test_browser.py` and confirm all tests pass.

## 5. Refactor + housekeeping (green)

- [x] 5.1 Re-run `uv run pytest task2/tests/` to confirm the existing `llm.py` tests still pass.
- [x] 5.2 Run `uv run ruff check task2/` and `uv run ruff format task2/`; resolve any findings.
- [x] 5.3 Inspect `agent/browser.py` for one-shot helper functions or premature abstractions and inline anything that is only called once (per repo conventions on minimalism).
- [x] 5.4 Verify `task2/README.md` setup section accurately describes `uv sync` + `uv run playwright install chromium` + `uv run pytest`.

## 6. Validation

- [x] 6.1 Run `openspec validate implement-browser-minimal --strict` and resolve any spec/format issues.
- [ ] 6.2 Stage commits in conventional-commit style (`feat(task2): ...`, `test(task2): ...`, `chore(task2): ...`) preserving real history (no squash-the-world).
