## Why

`loop.py` currently builds its observation as `body.innerText[:2000]` — a raw text dump that is noisy, token-heavy, and structurally blind: decorative prose overwhelms interactive elements, and the LLM cannot distinguish a button from a paragraph. The plan spec (`observe.py`, architecture component #4) calls for a compact AX-tree digest so the LLM sees only interactable nodes + headings, bounded by token caps, with last-action context threaded between steps.

## What Changes

- New module `task2/agent/observe.py` — produces `build_observation(browser, last_action) -> dict` with keys `url`, `title`, `ax_tree_digest`, `ax_fingerprint`, and `last_action`. Filters the Playwright accessibility tree to a canonical role set (button, link, textbox, combobox, checkbox, radio, tab, menuitem, option, plus heading roles h1–h6). Caps node count at `MAX_NODES` and accessible-name length at `MAX_NAME_LEN` (module-level constants).
- `task2/agent/loop.py` — replace the `_observe()` inline `innerText` construction with a call to `observe.build_observation(browser, last_action)`. The returned `ax_tree_digest` string populates `ObservationEvent.ax_tree_digest` (already defined in `trace.py`). `last_action` is `None` on the first step and `{tool, intent, outcome, error?}` on subsequent steps.
- New fixture `task2/tests/fixtures/observe_mixed.html` — a page with decorative `<div>`s, real `<button>`s, links, and headings; used by unit tests.
- New test file `task2/tests/agent/test_observe.py` — four acceptance tests (see Capabilities).
- **No other modules changed.**

## Capabilities

### New Capabilities

- `ax-tree-observation`: Compact accessibility-tree digest for the agent prompt. Filters to interactable roles + headings, caps node count and name length, formats as a human-readable string (one node per line: `[role] "name"`), computes an `ax_fingerprint` (SHA-256 of the canonical digest), and threads `last_action` alongside URL and title. Populates `ObservationEvent.ax_tree_digest`.

### Modified Capabilities

- `agent-loop`: The `_observe()` helper in `loop.py` is replaced by `observe.build_observation(browser, last_action)`. The observation dict now contains `ax_tree_digest` (AX tree string) instead of `text` (innerText). The state message serialized into the LLM message thread changes shape accordingly.

## Impact

- **Code**: `task2/agent/observe.py` (new); `task2/agent/loop.py` (modified `_observe` helper and step loop); `task2/tests/agent/test_observe.py` (new); `task2/tests/fixtures/observe_mixed.html` (new).
- **Dependencies**: No new packages. `observe.py` uses only `playwright.sync_api`, `hashlib`, and stdlib; both are already available.
- **`trace.py`**: `ObservationEvent.ax_tree_digest: str` is already defined — no model changes needed.
- **`browser.py`**: The Playwright `Page` object is accessible via `browser._page`; `observe.py` will call `page.accessibility.snapshot()` on it. No new public methods needed on `Browser`.
- **Existing tests**: `test_loop.py` mocks the LLM and does not inspect `ax_tree_digest` content; the shape change to the observation dict may require updating the `STATE_MESSAGE_PREFIX` assertion in `test_loop.py` if it checks exact JSON keys.
