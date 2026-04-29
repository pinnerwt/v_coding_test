## MODIFIED Requirements

### Requirement: `goto(url)` navigates the owned page

The system SHALL provide `Browser.goto(url: str) -> None` that navigates the owned page to the given URL and waits for the `domcontentloaded` lifecycle event (DOM ready, NOT all subresources) before returning. The navigation SHALL be bounded by an explicit `timeout=15000` (ms). On navigation failure (network error, invalid URL, timeout), `goto` SHALL raise `NavigationError` carrying the underlying message.

When the underlying `PlaywrightError` message matches the transient-error pattern `net::ERR_NETWORK_CHANGED|net::ERR_NETWORK_IO_SUSPENDED|net::ERR_INTERNET_DISCONNECTED|Page.goto.*Timeout`, `goto` SHALL sleep 250 ms and retry the navigation exactly once before raising. The retry SHALL use the same `wait_until="domcontentloaded"` and `timeout=15000`. On second failure, `goto` SHALL raise `NavigationError` as usual. Non-matching errors SHALL be raised immediately without retry.

#### Scenario: Returns after DOMContentLoaded even when a subresource hangs

- **GIVEN** a fixture HTTP server that serves an HTML body containing `<img src="/slow.png">` immediately, but holds the `GET /slow.png` response for 8 seconds before returning 200
- **WHEN** a caller invokes `b.goto(url)` against that server
- **THEN** the call SHALL return within 3 seconds (it does not wait for the slow image to finish loading)

#### Scenario: Raises NavigationError when DOMContentLoaded does not fire within 15 seconds

- **GIVEN** a fixture HTTP server that holds the HTML response itself for 20 seconds before any byte is sent
- **WHEN** a caller invokes `b.goto(url)` against that server
- **THEN** the call SHALL raise `NavigationError` within 31 seconds (15s timeout, with slack for the transient-retry path)

#### Scenario: Underlying Page.goto receives wait_until=domcontentloaded and timeout=15000

- **GIVEN** a `Page` stub that records `**kwargs` of each `goto` call
- **WHEN** a caller invokes `Browser.goto(url)` using that stub
- **THEN** the recorded kwargs SHALL include `wait_until="domcontentloaded"`
- **AND** the recorded kwargs SHALL include `timeout=15000`
