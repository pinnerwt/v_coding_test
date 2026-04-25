## Context

Task 2's plan (`task2/plan.md` §Architecture) calls for `agent/browser.py` as a "small Playwright tool surface exposed to the LLM." Ticket #2 carves out the smallest TDD slice: `goto` + `read("h1")` against a local fixture served by `http.server`.

Current state: `task2/agent/` contains only `llm.py`. No browser, no fixtures, no Playwright dependency. The agent loop, observer, locator pipeline, and supervisor all sit downstream of this module — they need *something* that knows how to drive a page before they have anything to test against.

Constraints worth naming:
- **Real Playwright in tests, not mocked.** CLAUDE.md's TDD rules forbid mocking the thing under test. The thing under test here is "we can drive Chromium from Python"; mocking Playwright would only test that we know how to call our own wrappers. The test must fail in a meaningful way if Playwright is misused.
- **No hosted external pages in tests.** Tests serve fixtures from `http.server` on an ephemeral port for determinism and offline CI.
- **Browser cost is real.** Launching Chromium per test is slow; we need session-scoped fixtures so the cost is paid once.
- **Future tickets extend this surface.** The shape we pick now must accommodate `click`, `type`, `read(intent)` (intent-based), `screenshot`, etc. without rework. Ticket #3 (locator L1) will add intent-based resolution on top.

## Goals / Non-Goals

**Goals:**
- A minimal, sync-style `Browser` Python class wrapping Playwright with two methods: `goto(url)` and `read(selector)`.
- Context-manager lifecycle so the Playwright runtime, browser, context, and page are owned and torn down deterministically.
- A reusable test fixture pattern: a static HTML directory served by `http.server` on a free port, exposed as a `pytest` fixture that yields the base URL.
- Test coverage for both happy path (`goto` then `read("h1")` returns the visible text) and the missing-selector case (`read` of a selector that matches nothing raises a typed error the loop can later catch).

**Non-Goals:**
- Intent-based locator resolution (`read("the page heading")`) — that is `agent/locate.py`, ticket #3.
- `click`, `type`, `select`, `wait_for`, `back`, `screenshot`, `done`, `fail` — separate tickets.
- Async API. The plan describes a synchronous tool surface called by the LLM loop; we use Playwright's sync API to keep the integration simple.
- Multiple tabs / contexts. One page per `Browser` instance for now; multi-context is out of scope per `task2/plan.md` §Non-goals.
- Network mocking, request interception, or auth state.

## Decisions

### Sync Playwright API over async

`playwright.sync_api` over `playwright.async_api`. The agent loop is naturally sequential (observe → decide → act → observe) and FastAPI can run sync handlers on a worker thread. Async would force every consumer into `await`, complicate the test surface, and buy nothing because there's only one page in flight per request. Trade-off: we can't multiplex multiple pages within one event loop, but that's a `plan.md` non-goal.

### Browser as a context manager, not a singleton

`with Browser() as b: b.goto(...); b.read(...)` rather than module-level globals. Each FastAPI request will own its own `Browser`, matching `plan.md` §Deployment ("one headless browser per request, recycled within a worker"). The context manager guarantees `playwright.stop()` runs on exceptions; a singleton would leak Chromium processes on test failure.

### `read(selector)` returns `str`, raises on no-match

`read` takes a CSS selector and returns the trimmed visible text of the *first* match. If zero elements match, it raises `ElementNotFound` (a module-local exception type). Rationale: the supervisor (ticket #8) needs a typed signal to classify "LocatorMiss"; returning `None` or `""` would conflate "element exists but is empty" with "element absent." Multiple matches → take the first; ambiguity-handling is `locate.py`'s job, not `browser.py`'s.

Alternative considered: return `Optional[str]`. Rejected because it pushes "missing vs empty" disambiguation onto every caller and makes the supervisor's classification noisier.

### Headless Chromium only

`p.chromium.launch(headless=True)`. The plan pins Chromium (`mcr.microsoft.com/playwright/python:latest` base image; "Mobile / non-Chromium browsers" listed as non-goal). Headless because tests run in CI and the deployed Zeabur worker has no display.

### Fixture HTTP server: stdlib `http.server` in a thread

A small `pytest` fixture spins up `http.server.ThreadingHTTPServer` on `("127.0.0.1", 0)` (ephemeral port), serving from `task2/tests/fixtures/`, and yields the base URL. Session-scoped so we pay the bind cost once. Stdlib only — no `pytest-httpserver` or similar — keeps the dep tree thin and the failure modes obvious.

Alternative considered: serve via `playwright.route()` or `data:` URLs. Rejected: real HTTP exercises the navigation path, including DNS-style hostname handling and same-origin behavior, which is what the test is supposed to validate.

### Playwright at session scope; `Browser` per test

The `playwright.sync_api` runtime and the launched Chromium *browser* live at session scope (one launch per test session). Each test gets a fresh `BrowserContext` and `Page`. This is the official Playwright recommendation for pytest and matches the pattern `pytest-playwright` uses internally — we just avoid the plugin to keep our surface minimal.

Our public `Browser` class wraps a fresh context+page. Tests instantiate `Browser(playwright_browser)` (the session-scoped Chromium). Production code instantiates `Browser()` which owns its own runtime.

### Module-local exceptions in `agent/browser.py`

`ElementNotFound` lives in `agent/browser.py`. We don't introduce a shared `agent/errors.py` yet — there's only one consumer. Ticket #8 (supervisor) can promote shared error types when a second module needs them.

## Risks / Trade-offs

- **Playwright install isn't covered by `uv sync`.** Users (and CI) need `uv run playwright install chromium` after `uv sync`. → Document in `task2/README.md` (or a setup note) and surface in the test failure message if Chromium is missing.
- **Sync API blocks the event loop if used inside async code.** Future FastAPI handlers need to call `Browser` from a thread pool. → Acceptable; we'll wire that up in ticket #14, not now.
- **Session-scoped Chromium leaks state across tests if a test mutates it.** With one page per `Browser` and per-test contexts, this is contained. → Tests must not stash global state on the shared Playwright instance.
- **`read` returning first-match silently picks one of N.** This is fine for the minimal slice (fixture has one `<h1>`), but production code will call `locate.py` instead. → `read(selector)` is documented as "raw selector, first match" and will be superseded by intent-based `read(intent)` in a later ticket.
- **`http.server` is single-threaded by default.** Using `ThreadingHTTPServer` avoids hangs if the test asks for two resources concurrently (favicon + page). → Already addressed in the Decisions section.
- **Adding `playwright` adds ~80MB to the venv plus ~150MB of browser binaries.** Unavoidable for Task 2. → No mitigation needed; this is inherent to the brief.
