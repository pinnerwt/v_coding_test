## Why

Task 2's agent loop needs a Playwright-backed browser tool surface (per `task2/plan.md` §Architecture, `agent/browser.py`). The plan's ticket #2 carves out the smallest red→green slice: prove we can drive a real Chromium page from Python via Playwright with two operations — navigate to a URL and read text by CSS selector — exercised against a local fixture served by `http.server`. This is the foundation every later locator/observation/loop ticket builds on; without it none of L1–L4 in `agent/locate.py` have anything to act against.

## What Changes

- Add `agent/browser.py` exposing a minimal `Browser` class with two methods: `goto(url)` and `read(selector)` (returns the visible text of the first match).
- `Browser` SHALL be a context manager that owns a single Chromium page across calls and tears down the Playwright runtime cleanly on exit.
- Add a pytest fixture under `task2/tests/fixtures/` containing a static HTML page with a known `<h1>` (and at least one other readable element) plus a pytest fixture that serves it via `http.server` on an ephemeral port.
- Add `task2/tests/test_browser.py` covering the happy path (`goto` then `read("h1")` returns the expected text) and the missing-selector case.
- Add `playwright` to `task2/pyproject.toml`. Document `uv run playwright install chromium` as a one-time post-install step in `task2/README.md` (or task2 setup notes if README doesn't exist yet).

Out of scope for this change: `click`, `type`, `select`, `wait_for`, `back`, `screenshot`, `done`, `fail`, intent-based locator resolution (those are tickets 3–11). `read` here takes a raw CSS selector; intent-based `read(intent?)` lands with `locate.py`.

## Capabilities

### New Capabilities

- `browser-tool`: minimal Playwright-backed browsing surface — page lifecycle (open/close), navigation (`goto`), and selector-based text extraction (`read`). Future tickets extend this capability with the rest of the tool surface listed in `plan.md` §Architecture point 2.

### Modified Capabilities

(none)

## Impact

- **Code**: new module `task2/agent/browser.py`; new test module `task2/tests/test_browser.py`; new fixture HTML under `task2/tests/fixtures/`.
- **Dependencies**: adds `playwright` (runtime) to `task2/pyproject.toml`; CI / local dev needs `uv run playwright install chromium`.
- **Runtime cost**: tests launch a real headless Chromium per test session; we'll scope the Playwright fixture to session scope to keep wall-clock manageable.
- **Deployment**: no Zeabur impact yet — the agent loop isn't wired up. The base image (`mcr.microsoft.com/playwright/python:latest`, per `plan.md` §Deployment) already ships browsers, so the deploy story is unchanged.
- **No public API surface yet**: this module is internal; FastAPI routes land in ticket #14.
