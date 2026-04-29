# Implementation tasks

## 1. Failing test (red)

- [x] 1.1 In `task2/tests/test_loop.py`, add a test that forces the click branch into the `playwright.sync_api.TimeoutError` path (e.g. via a stub Page+Locator whose `click(timeout=...)` raises `PlaywrightTimeoutError("Locator.click: Timeout 5000ms exceeded.")`) and asserts that the emitted `ActEvent.diff` equals `{"error": "TimeoutError: Locator.click: Timeout 5000ms exceeded."}`. Confirm with `uv run pytest task2/tests/test_loop.py::<new-test> -x` that it fails on the current `diff={}` producer.
- [x] 1.2 Add a sibling test for the type branch using `PlaywrightTimeoutError("Locator.fill: Timeout 5000ms exceeded.")` against the type dispatch.
- [x] 1.3 Optionally add a generic `PlaywrightError("Element is not attached to the DOM")` test for the click branch, asserting `ActEvent.diff["error"]` starts with the playwright base class name and contains the message text.

## 2. Production change (green)

- [x] 2.1 In `task2/agent/loop.py` `_emit_act_event`, add a keyword-only `diff: dict[str, Any] | None = None` parameter; default-normalise to `{}` inside the function body and pass to `ActEvent(...)`.
- [x] 2.2 In the click branch of `_dispatch`, change `except PlaywrightTimeoutError:` to `except PlaywrightTimeoutError as exc:` and `except PlaywrightError:` to `except PlaywrightError as exc:`. Build `act_diff = {}` for `ok`/`nav` outcomes and `act_diff = {"error": f"{exc.__class__.__name__}: {exc}"}` for `timeout`/`error` outcomes.
- [x] 2.3 Pass `diff=act_diff` to the `_emit_act_event(...)` call in the click branch.
- [x] 2.4 Repeat 2.2 and 2.3 for the type branch.
- [x] 2.5 Run `uv run pytest task2/tests/test_loop.py -x` and confirm the new tests now pass.

## 3. Quality gates

- [x] 3.1 `cd task2 && uv run ruff check .` is clean.
- [x] 3.2 `cd task2 && uv run ruff format --check .` is clean.
- [x] 3.3 `cd task2 && uv run pytest` is clean (no pre-existing test regresses; `test_eval.py` synthetic-trace tests still classify `"unknown error"` because they construct `ActEvent(diff={})` directly — that path is preserved).

## 4. Smoke test

- [x] 4.1 Run `task2/smoke_test.sh` against the local Qwen and confirm exit 0.

## 5. Post-merge benchmark verification (manual, run by `/done_pr`)

- [ ] 5.1 The `/done_pr` step 1a webvoyager run SHALL write a results JSON. Inspect webvoyager-2's `failure_detail` in that JSON.
- [ ] 5.2 The `failure_detail` for webvoyager-2 (if it still fails with `failure_class=tool_error`) SHALL NOT be the literal string `"unknown error"`. It SHALL start with an exception class name (e.g. `"TimeoutError: ..."`, `"Error: ..."`) AND contain a message body. This is the acceptance gate for ticket #99.
- [ ] 5.3 If webvoyager-2 instead succeeds (pass_rate recovers to 2/3), that also satisfies the ticket — anchor preservation + the underlying playwright issue together resolved the case.
