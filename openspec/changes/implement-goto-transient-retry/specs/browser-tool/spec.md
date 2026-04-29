## MODIFIED Requirements

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
