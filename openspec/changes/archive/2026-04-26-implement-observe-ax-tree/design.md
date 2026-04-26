## Context

Tickets #1–#20 are complete. The agent loop runs tasks end-to-end and produces traces, but its observation of the current page is `body.innerText[:2000]` — a flat string that mixes prose, navigation text, and interactive elements indiscriminately. `ObservationEvent.ax_tree_digest` exists in `trace.py` but is never populated; the field sits empty in every recorded trace.

Playwright exposes `page.accessibility.snapshot()` which returns the full accessibility tree as a nested dict. That tree contains every visible node, including decorative spans and paragraphs. The task here is to filter, cap, and serialize it into a token-efficient string that the LLM can reliably reason about.

**As-built deviation**: `page.accessibility.snapshot()` does not exist in Playwright 1.58 (the version in use). The implementation uses the Chrome DevTools Protocol (CDP) command `Accessibility.getFullAXTree` via `page.context.new_cdp_session(page)` instead. The semantics are equivalent: a flat list of all AX nodes is returned, each with `role.value`, `name.value`, and `properties`. The filtering and serialization logic is identical to what the spec describes.

Existing code conventions: `from __future__ import annotations`, no docstrings in non-test code, no comments except for non-obvious `why`, frozen dataclasses for pure data (not used here — `observe.py` exposes a single function), `uv run ruff check .` must be clean.

The Playwright `accessibility.snapshot()` API returns a nested `dict | None`. Each node has `role`, `name` (accessible name), and `children` (list of child nodes). Interactable roles and heading roles are the filter criterion; all other roles are dropped. Playwright's role vocabulary uses lowercase strings (e.g. `"button"`, `"link"`, `"textbox"`). Heading levels (`h1`–`h6`) appear as role `"heading"` with a `level` property. The CDP `getFullAXTree` response uses the same role strings.

## Goals / Non-Goals

**Goals:**

- Implement `task2/agent/observe.py` with a single public function `build_observation(browser, last_action) -> dict` returning `{url, title, ax_tree_digest, ax_fingerprint, last_action}`.
- Filter the AX tree to canonical roles: `button`, `link`, `textbox`, `combobox`, `checkbox`, `radio`, `tab`, `menuitem`, `option`, `heading` (covers h1–h6).
- Cap output at `MAX_NODES` nodes (module-level constant, default 200) and `MAX_NAME_LEN` characters per accessible name (module-level constant, default 80).
- Compute `ax_fingerprint` as a SHA-256 hex digest of the canonical `ax_tree_digest` string.
- Thread `last_action` (a `{tool, intent, outcome, error?}` dict or `None`) through the observation dict.
- Replace `loop.py`'s inline `_observe()` helper with a call to `observe.build_observation(browser, last_action)`.
- Add `task2/tests/agent/test_observe.py` with four red-first tests.
- Add `task2/tests/fixtures/observe_mixed.html` — a page with decorative `<div>`s, real `<button>`s, links, and headings.

**Non-Goals:**

- Nested tree rendering (indented children). Flat list of matched nodes is sufficient for token efficiency; the LLM does not need parent–child structure for the roles in scope.
- Snapshot caching across steps. Each call to `build_observation()` re-runs `page.accessibility.snapshot()`.
- Screenshot capture or `screenshot_ref` population (separate module).
- Viewport reporting in `observe.py` (left for the trace integration layer to add).
- Integration with `TraceWriter` / `ObservationEvent` (separate ticket).

## Decisions

### Decision 1: Flat serialization format — `[role] "name"` one node per line

The `ax_tree_digest` string uses one line per kept node in the form `[role] "name"`. Heading nodes include their level: `[heading:2] "Introduction"`. This is maximally compact and readable by the LLM without requiring JSON parsing. Nodes with an empty or absent accessible name are included with name `""` (empty quoted string) so the LLM knows an interactive element exists even if it has no label.

**Alternative considered**: JSON array of `{role, name}` objects. Rejected because JSON encoding adds ~20% token overhead (`{"role":"button","name":"Submit"}` vs `[button] "Submit"`), and the LLM does not need random access into the structure — it reads linearly.

**Alternative considered**: Indented tree with parent–child nesting. Rejected because the tree can be arbitrarily deep and nesting multiplies token count. Flat list of interactables is sufficient for decision-making.

### Decision 2: Role filter as a `frozenset` constant — `INTERACTABLE_ROLES`

A module-level `frozenset` named `INTERACTABLE_ROLES` holds the canonical string set: `{"button", "link", "textbox", "combobox", "checkbox", "radio", "tab", "menuitem", "option", "heading"}`. Tests reference this constant directly so tests and implementation cannot diverge. Adding a new role in future requires changing one line.

**Alternative considered**: inline `if role in {...}` in the filter function. Rejected because tests cannot reference an anonymous set to verify the canonical list, and extending the set requires a code search.

### Decision 3: Recursive DFS with early-exit at `MAX_NODES`

`page.accessibility.snapshot()` returns a nested tree. The filter walks it depth-first, appending matching nodes to a flat list. Once the list reaches `MAX_NODES` entries, the walk short-circuits and appends a sentinel line `[... N more nodes truncated]`. This bounds both traversal cost and output length.

**Alternative considered**: Collect all matching nodes first, then truncate. Rejected because a 10,000-node page would still traverse fully before truncating. Early-exit is O(MAX_NODES) in the number of kept nodes.

### Decision 4: `build_observation` signature — `(browser: Browser, last_action: dict | None) -> dict`

The function accepts the `Browser` wrapper (not a raw `Page`) so it respects the same abstraction boundary as the rest of the codebase. It accesses `browser._page` internally — the same pattern used by `loop.py` today. If `browser._page is None` (browser closed or not started), the function returns a zero-observation dict: `{url: "", title: "", ax_tree_digest: "", ax_fingerprint: <sha256 of "">, last_action: last_action}`.

**Alternative considered**: Accept a raw `playwright.sync_api.Page`. Rejected because the public module boundary is `Browser`; exposing `_page` only within `observe.py` keeps the coupling explicit and co-located.

### Decision 5: `ax_fingerprint` — SHA-256 of `ax_tree_digest`

`hashlib.sha256(ax_tree_digest.encode()).hexdigest()` gives a 64-char hex string. This matches the `ax_fingerprint: str` field in `ObservationEvent` and is sufficient for drift detection (fingerprint changes when any interactable node role or name changes). No salting needed — the fingerprint is not a security hash.

### Decision 6: Loop integration — pass `last_action` from the previous step

`loop.py` tracks `last_action: dict | None` across iterations. After each tool dispatch, `last_action` is set to `{tool: <name>, intent: <args summary>, outcome: <"ok"|"error">, error?: <msg>}`. On the first step it is `None`. `_observe(browser)` becomes `observe.build_observation(browser, last_action)`. The returned dict is serialized to JSON and appended to the message thread as before, but keys are now `url`, `title`, `ax_tree_digest`, `last_action` (instead of `url`, `text`).

The `STATE_MESSAGE_PREFIX` constant in `loop.py` stays; only the observation dict shape changes. Existing `test_loop.py` tests that do not inspect observation key names will stay green; any test that asserts `"text"` in the observation JSON will need updating (the key becomes `ax_tree_digest`).

## Risks / Trade-offs

- **`page.accessibility.snapshot()` is slow on large DOMs.** The Playwright AX tree snapshot can take 50–200 ms on complex pages. Acceptable: the agent loop is I/O-bound on LLM calls (typically 2–10 s); AX snapshot overhead is negligible. If profiling shows otherwise, caching the snapshot within a step is straightforward.
- **`page.accessibility.snapshot()` returns `None` for pages with no AX tree** (e.g. blank `about:blank`, or cross-origin iframes that block AX). The function handles `None` by returning an empty digest, same as the browser-closed case. The LLM will see an empty observation and should call `goto` to navigate.
- **Flat serialization loses parent context.** A `<button>` inside a `<nav>` looks identical to one in `<main>`. In practice, accessible names are scoped sufficiently; if not, the LLM can use `read(intent=...)` to get element text for disambiguation. This is an acceptable trade-off for the token savings.
- **`loop.py` state-message shape change.** Existing integration tests (`test_loop.py`) that mock the LLM do not inspect the observation content — they only verify `RunResult` shape and status. However, the `_observe` function's return dict now has `ax_tree_digest` instead of `text`; any test asserting the exact JSON content of the user message will break. These tests are in `test_loop.py` and must be reviewed and updated in the tasks.

## Open Questions

(none — all decisions resolved above)
