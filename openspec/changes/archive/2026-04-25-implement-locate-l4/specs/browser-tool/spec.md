## ADDED Requirements

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
