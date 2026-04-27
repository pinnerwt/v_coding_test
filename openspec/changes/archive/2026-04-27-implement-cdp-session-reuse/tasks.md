## 1. Failing tests (red bar)

- [x] 1.1 In `task2/tests/agent/test_observe.py`, add `test_cdp_session_reused_across_n_observations`: use `unittest.mock.patch.object` to spy on `page.context.new_cdp_session`; call `build_observation` 10 times on the same browser; assert `new_cdp_session` call count == 1 and all 10 observations have non-empty `ax_tree_digest`. Run `cd task2 && uv run pytest tests/agent/test_observe.py::test_cdp_session_reused_across_n_observations -x` — must fail (ImportError or AttributeError on missing cache).
- [x] 1.2 In `task2/tests/agent/test_observe.py`, add `test_new_page_invalidates_cached_session`: navigate to page A, call `build_observation` once (session cached), then simulate a new page by replacing `browser._page` with a fresh page object obtained via `browser._context.new_page()`; call `build_observation` again; assert `new_cdp_session` call count == 2. Run — must fail.
- [x] 1.3 In `task2/tests/agent/test_observe.py`, add `test_browser_exit_detaches_without_raising`: enter a `Browser` context, call `build_observation` to prime the cache, then exit the `with` block; assert no exception is raised and `browser._cdp_sessions` is empty (accessed after exit). Run — must fail (cache attribute missing).
- [x] 1.4 Run `cd task2 && uv run pytest tests/agent/test_observe.py -x` — confirm only the three new tests fail and all existing tests still pass.

## 2. Browser._cdp_sessions attribute

- [x] 2.1 In `task2/agent/browser.py`, add `self._cdp_sessions: dict = {}` to `Browser.__init__` (after `self._page = None`). Run `uv run ruff check .` — must be clean.
- [x] 2.2 In `Browser.__exit__`, before `context.close()`, iterate `self._cdp_sessions.values()` and call `detach()` on each inside a `try/except Exception` that passes silently; then clear `self._cdp_sessions`. Run `uv run ruff check . && uv run ruff format .` — clean.

## 3. _ax_nodes cache logic

- [x] 3.1 In `task2/agent/observe.py`, change `_ax_nodes(page)` signature to `_ax_nodes(browser)`. Update the body: obtain the page via `page = browser._page` and the cache via `sessions = browser._cdp_sessions` (direct read — all browser-like callers initialize the attribute). `StubBrowser` in `agent/replay.py` SHALL also initialize `self._cdp_sessions: dict = {}` to satisfy the contract.
- [x] 3.2 In `_ax_nodes`: check if `id(page)` is a key in `sessions`. If not, evict all stale entries (iterate values, detach each silently, then clear the dict) and open a fresh session with `page.context.new_cdp_session(page)`, store under `sessions[id(page)]`. If `id(page)` is already a key, reuse the existing session. Do NOT call `detach()` inside `_ax_nodes` when reusing a cached session. If `cdp.send(...)` raises on a cached session, detach and pop `sessions[id(page)]` before returning `([], 0)` so a transient failure does not poison the cache.
- [x] 3.3 Update `build_observation` to call `_ax_nodes(browser)` instead of `_ax_nodes(page)`. Update the existing `fake_browser` namespace in `test_build_observation_falls_back_when_new_cdp_session_raises` to include `_cdp_sessions={}` so it exercises the `new_cdp_session` error branch under the cached-mode contract.
- [x] 3.4 Run `uv run ruff check . && uv run ruff format .` from `task2/` — clean.

## 4. Green bar

- [x] 4.1 Run `cd task2 && uv run pytest tests/agent/test_observe.py -x` — all tests including the three new ones must pass.
- [x] 4.2 Run `cd task2 && uv run pytest -x` — full suite must be green (no regressions).
- [x] 4.3 Run `cd task2 && uv run ruff check . && uv run ruff format --check .` — clean.

## 5. Pre-commit gate

- [x] 5.1 Run `cd task2 && uv run ruff format . && uv run ruff check . && uv run pytest` — all three commands exit 0. Only then commit.
