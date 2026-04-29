# browser-tool Specification

## Purpose
TBD - created by archiving change implement-browser-minimal. Update Purpose after archive.
## Requirements
### Requirement: Browser lifecycle as a context manager

The system SHALL expose a `Browser` class that owns a Playwright runtime, a launched Chromium browser, a single browser context, and a single page for its lifetime. `Browser` SHALL implement the context-manager protocol: `__enter__` returns the browser instance ready to navigate; `__exit__` SHALL stop the Playwright runtime and release all owned resources, even when the `with` block exits via an exception.

#### Scenario: Constructs and tears down cleanly

- **WHEN** a caller uses `with Browser() as b:` and the block completes normally
- **THEN** entering the block SHALL launch a headless Chromium and create one page
- **AND** exiting the block SHALL stop the Playwright runtime
- **AND** subsequent calls on `b` (e.g. `b.read(...)`) SHALL raise `BrowserClosed`

#### Scenario: Tears down on exception inside the with-block

- **WHEN** a caller uses `with Browser() as b:` and the block raises `RuntimeError("boom")`
- **THEN** the original `RuntimeError` SHALL propagate to the caller
- **AND** the Playwright runtime SHALL be stopped (no leaked Chromium process)

### Requirement: `goto(url)` navigates the owned page

The system SHALL provide `Browser.goto(url: str) -> None` that navigates the owned page to the given URL and waits for the `load` lifecycle event before returning. On navigation failure (network error, invalid URL), `goto` SHALL raise `NavigationError` carrying the underlying message.

When the underlying `PlaywrightError` message matches the transient-error pattern `net::ERR_NETWORK_CHANGED|net::ERR_NETWORK_IO_SUSPENDED|net::ERR_INTERNET_DISCONNECTED|Page.goto.*Timeout`, `goto` SHALL sleep 250 ms and retry the navigation exactly once before raising. On second failure, `goto` SHALL raise `NavigationError` as usual. Non-matching errors SHALL be raised immediately without retry.

#### Scenario: Navigates to a reachable URL

- **WHEN** a caller invokes `b.goto("http://127.0.0.1:<port>/index.html")` against a running fixture server
- **THEN** the call SHALL return without raising
- **AND** the page's current URL SHALL match the requested URL

#### Scenario: Reports navigation failure

- **WHEN** a caller invokes `b.goto("http://127.0.0.1:1/never-listening")`
- **THEN** the call SHALL raise `NavigationError`
- **AND** the exception message SHALL include the failing URL

#### Scenario: Retries once on transient Chromium network error and succeeds

- **GIVEN** a `Page` stub whose first `goto` call raises `PlaywrightError("net::ERR_NETWORK_CHANGED")` and whose second `goto` call returns normally
- **WHEN** a caller invokes `Browser.goto(url)` using that stub
- **THEN** the call SHALL return without raising
- **AND** `Page.goto` SHALL have been called exactly twice

#### Scenario: Non-transient error is not retried

- **GIVEN** a `Page` stub whose `goto` call raises `PlaywrightError("net::ERR_NAME_NOT_RESOLVED")`
- **WHEN** a caller invokes `Browser.goto(url)` using that stub
- **THEN** the call SHALL raise `NavigationError` immediately
- **AND** `Page.goto` SHALL have been called exactly once

#### Scenario: Second failure after transient retry raises NavigationError

- **GIVEN** a `Page` stub whose first `goto` call raises `PlaywrightError("net::ERR_NETWORK_CHANGED")` and whose second `goto` call raises `PlaywrightError("net::ERR_NETWORK_CHANGED")` as well
- **WHEN** a caller invokes `Browser.goto(url)` using that stub
- **THEN** the call SHALL raise `NavigationError`
- **AND** `Page.goto` SHALL have been called exactly twice

### Requirement: `read(selector)` returns visible text of first match

The system SHALL provide `Browser.read(selector: str) -> str` that returns the trimmed visible text of the first DOM element matching the given CSS selector on the currently loaded page. Leading and trailing whitespace SHALL be stripped; internal whitespace SHALL be preserved as-rendered (no normalization beyond `.strip()`). When zero elements match, `read` SHALL raise `ElementNotFound` carrying the selector.

#### Scenario: Returns visible text of a present element

- **GIVEN** the page contains `<h1>Hello, world</h1>`
- **WHEN** a caller invokes `b.read("h1")`
- **THEN** the call SHALL return `"Hello, world"`

#### Scenario: Strips surrounding whitespace

- **GIVEN** the page contains `<h1>\n  Hello\n</h1>`
- **WHEN** a caller invokes `b.read("h1")`
- **THEN** the call SHALL return `"Hello"`

#### Scenario: Raises when no element matches

- **GIVEN** the page contains no element matching `.does-not-exist`
- **WHEN** a caller invokes `b.read(".does-not-exist")`
- **THEN** the call SHALL raise `ElementNotFound`
- **AND** the exception message SHALL include the selector `".does-not-exist"`

#### Scenario: Returns first match when multiple elements match

- **GIVEN** the page contains `<p>first</p><p>second</p>`
- **WHEN** a caller invokes `b.read("p")`
- **THEN** the call SHALL return `"first"`

### Requirement: Module-local exception types

The system SHALL define `NavigationError`, `ElementNotFound`, and `BrowserClosed` as exception classes in `agent.browser`, all subclasses of a common `BrowserError` base. These exception types SHALL be importable directly from `agent.browser` so callers can catch them by type.

#### Scenario: Exception types are importable and form a hierarchy

- **WHEN** a caller executes `from agent.browser import BrowserError, NavigationError, ElementNotFound, BrowserClosed`
- **THEN** the import SHALL succeed
- **AND** `NavigationError`, `ElementNotFound`, and `BrowserClosed` SHALL each be subclasses of `BrowserError`

### Requirement: `screenshot()` captures the current viewport as PNG bytes

The system SHALL provide `Browser.screenshot(*, full_page: bool = False) -> bytes` that returns the raw PNG-encoded bytes of the currently loaded page. When `full_page=False` (the default), the screenshot SHALL cover only the current viewport. When `full_page=True`, the screenshot SHALL cover the entire scrollable page. When the browser is not open (the `Browser` is not inside a `with` block), `screenshot` SHALL raise `BrowserClosed`. The bytes returned SHALL be a valid PNG (i.e. begin with the PNG signature `89 50 4E 47 0D 0A 1A 0A`).

#### Scenario: Returns viewport PNG bytes when called inside the with-block

- **GIVEN** a `Browser` instance inside a `with` block, with the page navigated to a fixture
- **WHEN** a caller invokes `b.screenshot()`
- **THEN** the call SHALL return a non-empty `bytes` value
- **AND** the value SHALL begin with the PNG signature `b'\x89PNG\r\n\x1a\n'`

#### Scenario: Raises BrowserClosed when called after the with-block exits

- **GIVEN** a `Browser` instance whose `with` block has exited
- **WHEN** a caller invokes `b.screenshot()`
- **THEN** the call SHALL raise `BrowserClosed`

#### Scenario: full_page=True captures beyond the viewport

- **GIVEN** a `Browser` instance inside a `with` block, with the page navigated to a fixture taller than the viewport
- **WHEN** a caller invokes `b.screenshot(full_page=True)` and then `b.screenshot(full_page=False)`
- **THEN** both calls SHALL return non-empty PNG bytes
- **AND** the `full_page=True` byte length SHALL be greater than or equal to the `full_page=False` byte length

### Requirement: `click_at(x, y)` clicks at viewport-relative pixel coordinates

The system SHALL provide `Browser.click_at(x: int, y: int) -> None` that issues a left-mouse click at the given viewport-relative pixel coordinates via Playwright's `page.mouse.click(x, y)` API. The click SHALL be a single left-button down/up sequence at the specified coordinates without prior mouse movement (Playwright's default `click` semantics). When the browser is not open, `click_at` SHALL raise `BrowserClosed`. `click_at` SHALL NOT validate the coordinates against the viewport bounds — out-of-bounds clicks are Playwright's responsibility, and the locator pipeline (L4) is the layer that bounds-checks.

#### Scenario: Click at coordinates fires the page's click handler

- **GIVEN** a fixture page that registers `document.addEventListener('click', e => { window.__last_click = {x: e.clientX, y: e.clientY}; })`
- **AND** a `Browser` instance inside a `with` block, navigated to that fixture
- **WHEN** a caller invokes `b.click_at(150, 250)`
- **THEN** the call SHALL return without raising
- **AND** `b._page.evaluate("() => window.__last_click")` SHALL return a dict equal to `{"x": 150, "y": 250}`

#### Scenario: Click at coordinates inside a target element invokes that element's handler

- **GIVEN** a fixture page containing a `<div id="target">` painted at viewport rect `(100, 200, 80, 40)` with a click handler that sets `window.__target_clicked = true`
- **AND** a `Browser` instance inside a `with` block, navigated to that fixture
- **WHEN** a caller invokes `b.click_at(140, 220)` (the bbox center)
- **THEN** `b._page.evaluate("() => window.__target_clicked")` SHALL return `True`

#### Scenario: Raises BrowserClosed when called after the with-block exits

- **GIVEN** a `Browser` instance whose `with` block has exited
- **WHEN** a caller invokes `b.click_at(10, 20)`
- **THEN** the call SHALL raise `BrowserClosed`

