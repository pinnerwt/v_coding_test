## ADDED Requirements

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

#### Scenario: Navigates to a reachable URL

- **WHEN** a caller invokes `b.goto("http://127.0.0.1:<port>/index.html")` against a running fixture server
- **THEN** the call SHALL return without raising
- **AND** the page's current URL SHALL match the requested URL

#### Scenario: Reports navigation failure

- **WHEN** a caller invokes `b.goto("http://127.0.0.1:1/never-listening")`
- **THEN** the call SHALL raise `NavigationError`
- **AND** the exception message SHALL include the failing URL

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
