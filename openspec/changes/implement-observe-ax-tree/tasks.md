## 1. Red — Failing Tests for observe.py

- [x] 1.1 Add `task2/tests/fixtures/observe_mixed.html` — a page with at least: one `<h2>` heading, one `<a href="#">` link, one `<button>`, one decorative `<div>` with visible text (no semantic role). This page is the shared fixture for tests 1.2, 1.4, and 1.5.
- [x] 1.2 Create `task2/tests/agent/test_observe.py`. Add `test_decorative_divs_excluded_buttons_included`: navigate to `observe_mixed.html`, call `build_observation(browser, None)`, assert `ax_tree_digest` contains a `[button]` line, assert it does NOT contain `generic` or `div` as a role.
- [x] 1.3 Add `test_1000_button_page_capped`: generate an in-memory HTML page with 1000 `<button>` elements, navigate browser to it (via `data:` URL or a per-test fixture server), call `build_observation(browser, None)`, assert the number of `[button]` lines equals `MAX_NODES`, assert the last line matches the sentinel pattern `\[... \d+ more nodes truncated\]`.
- [x] 1.4 Add `test_last_action_none_first_step`: call `build_observation(browser, None)` with a navigated browser, assert returned dict has `last_action` key equal to `None`.
- [x] 1.5 Add `test_last_action_threaded_second_step`: call `build_observation(browser, {"tool": "goto", "intent": "navigate", "outcome": "ok"})`, assert returned dict's `last_action` equals `{"tool": "goto", "intent": "navigate", "outcome": "ok"}`.
- [x] 1.6 Add `test_ax_tree_digest_round_trips_through_trace`: call `build_observation(browser, None)` on `observe_mixed.html`, extract `ax_tree_digest` and `ax_fingerprint`, construct an `ObservationEvent` using them, round-trip via `model_dump_json()` → `ObservationEvent.model_validate_json()`, assert round-tripped `ax_tree_digest` equals original, assert round-tripped `ax_fingerprint` equals original.
- [x] 1.7 Run `uv run pytest task2/tests/agent/test_observe.py -x` from `task2/` and confirm all tests fail with `ModuleNotFoundError` (the module does not exist yet).

## 2. Green — Implement observe.py

- [ ] 2.1 Create `task2/agent/observe.py` with `from __future__ import annotations` and imports: `hashlib`, `typing.TYPE_CHECKING`, and a conditional import of `Browser` for type checking only.
- [ ] 2.2 Define module-level constants: `INTERACTABLE_ROLES: frozenset[str]` (the 10-element canonical set per spec), `MAX_NODES: int = 200`, `MAX_NAME_LEN: int = 80`.
- [ ] 2.3 Implement a private `_walk(node, collected, remaining)` recursive helper: if `node` is `None` or `remaining[0] <= 0`, return; if `node["role"]` is in `INTERACTABLE_ROLES`, append to `collected` and decrement `remaining[0]`; recurse into `node.get("children", [])`.
- [ ] 2.4 Implement a private `_serialize(nodes, total_found)` function: for each node, format as `[role] "name"` (or `[heading:N] "name"` if role is `heading` and `level` key exists); truncate name to `MAX_NAME_LEN` chars with `…` suffix if exceeded; join with `\n`; if `total_found > MAX_NODES`, append `\n[... {total_found - MAX_NODES} more nodes truncated]`.
- [ ] 2.5 Implement `build_observation(browser, last_action)`: access `browser._page`; if `None`, return zero-observation dict; call `page.accessibility.snapshot()`; if snapshot is `None`, treat as empty tree; run `_walk` with `remaining=[MAX_NODES]` and a separate full-count pass to get `total_found` (or count during walk); call `_serialize`; compute `ax_fingerprint = hashlib.sha256(ax_tree_digest.encode()).hexdigest()`; return `{"url": page.url, "title": page.title(), "ax_tree_digest": ax_tree_digest, "ax_fingerprint": ax_fingerprint, "last_action": last_action}`.
- [ ] 2.6 Run `uv run pytest task2/tests/agent/test_observe.py -x` from `task2/` and confirm all tests pass.

## 3. Red — Failing Loop Integration Tests

- [ ] 3.1 In `task2/tests/agent/test_loop.py`, add `test_observation_contains_ax_tree_digest_key`: use a `_FakeLLMClient` that captures the messages list on the first `chat()` call (by storing `messages` as an attribute), then calls `done`. After the loop returns, assert that the second message in the captured messages list (index 1, the first user/observation message) has `"ax_tree_digest"` in its JSON content.
- [ ] 3.2 Add `test_observation_does_not_contain_legacy_text_key`: same setup, assert the observation message JSON does NOT contain the key `"text"`.
- [ ] 3.3 Add `test_first_step_last_action_null`: capture LLM messages; assert observation at step 1 has `"last_action": null` in JSON.
- [ ] 3.4 Add `test_second_step_last_action_populated`: use a `_FakeLLMClient` that: step 1 → `goto` tool call; step 2 → `done`. Capture the step-2 observation message (index after the step-1 tool result). Assert its JSON has `last_action` dict with key `tool` equal to `"goto"`.
- [ ] 3.5 Run `uv run pytest task2/tests/agent/test_loop.py -x -k "ax_tree or last_action"` from `task2/` and confirm the new tests fail (the loop still uses the old `_observe` helper at this point).

## 4. Green — Loop Integration

- [ ] 4.1 In `task2/agent/loop.py`, add `import agent.observe as observe` at the top (after existing imports).
- [ ] 4.2 Add a `last_action: dict | None = None` variable before the loop's `for` iteration.
- [ ] 4.3 Replace the call to `_observe(browser)` inside the loop with `observe.build_observation(browser, last_action)`.
- [ ] 4.4 After each successful tool dispatch (in `_dispatch` return, before appending tool result), set `last_action = {"tool": tool_name, "intent": str(args), "outcome": "ok"}`. On exception or error return from `_dispatch`, set `last_action = {"tool": tool_name, "intent": str(args), "outcome": "error", "error": <error string>}`. For `done` and `fail` terminal exits, `last_action` is not needed (loop exits immediately).
- [ ] 4.5 Remove the now-unused `_BODY_TEXT_JS`, `_BODY_TEXT_LIMIT`, `_body_text`, and `_observe` symbols from `loop.py` (they become dead code). Confirm no other module imports them before removing.
- [ ] 4.6 Run `uv run pytest task2/tests/agent/test_loop.py -x` from `task2/` and confirm all loop tests (old + new) pass.

## 5. Full Test Suite

- [ ] 5.1 Run `uv run pytest task2/tests/` from `task2/` and confirm all existing tests still pass — no regressions. Pay particular attention to `test_loop.py` tests that inspect message content (they may need the `"text"` key assertion replaced with `"ax_tree_digest"`).
- [ ] 5.2 If any `test_loop.py` test asserts the legacy `"text"` key in the observation JSON, update those assertions to use `"ax_tree_digest"` and confirm the tests are still valid regression guards (they must still fail if the loop reverts to the old observation).

## 6. Lint and Format

- [ ] 6.1 Run `uv run ruff check --fix .` from `task2/` to auto-fix any lint errors.
- [ ] 6.2 Run `uv run ruff format .` from `task2/` to auto-format changed files.
- [ ] 6.3 Run `uv run ruff check .` from `task2/` and confirm it exits clean (zero errors, zero warnings).

## 7. Refactor Under Green (if needed)

- [ ] 7.1 Review `_walk` for correctness with `MAX_NODES` early-exit: confirm that the sentinel count (`total_found - MAX_NODES`) is computed correctly even when the walk short-circuits. Add an assertion in the test for the sentinel number if not already checked.
- [ ] 7.2 Verify that `build_observation` with a closed browser (page is `None`) returns a valid dict that does not raise — confirm this is covered by the zero-observation scenario in the spec. Add a test if not already present.
- [ ] 7.3 Confirm `observe.py` has no docstrings or inline comments beyond any single non-obvious `why` comment. Remove any discovered during review.
