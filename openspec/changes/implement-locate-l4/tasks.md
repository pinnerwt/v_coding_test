## 1. Test fixtures (red prep)

- [x] 1.1 Create `task2/tests/fixtures/locate_l4_no_metadata.html`. Body contains exactly one clickable target rendered as a bare `<div id="target">` with **no** role attribute, **no** `aria-label`, **no** `aria-labelledby`, **no** wrapping `<label>`, **no** `title`, **no** text content, and **no** descendant text. Style the target via inline CSS so it has a known viewport pixel rect — recommended `position: fixed; left: 100px; top: 200px; width: 80px; height: 40px; background: #4a90e2;` so the bbox center `(140, 220)` is deterministic. The page SHALL register a JS click handler at document level that records the click coordinates: `document.addEventListener('click', e => { window.__l4_click = {x: e.clientX, y: e.clientY, target: e.target.id}; });`. The `<head>` SHALL include `<meta charset="utf-8">` and a `<title>L4 No Metadata</title>`. No `<button>`, `<a href>`, `<input>`, or other naturally accessible affordance SHALL be present anywhere on the page. The page SHALL contain a `<style>` block that hides any default focus outline on the target so the click test reads back coordinates only.
- [x] 1.2 Re-confirm by reading the fixture in a Python REPL: `Browser` opened on it, `page.get_by_role("button").count() == 0`, `page.get_by_role("link").count() == 0`, `page.get_by_role("textbox").count() == 0` — i.e. L1 sees zero candidates regardless of the intent we will pass. (This step is a sanity check; if any of those are non-zero, the fixture has accidentally exposed AX metadata and step 1.1 must be redone.)
- [x] 1.3 No conftest changes — `fixture_server` and `playwright_chromium` are reused.

## 2. Browser tool surface — failing tests (red)

- [x] 2.1 Add the screenshot tests to `task2/tests/agent/test_browser.py`:
  - `test_screenshot_returns_png_bytes_in_with_block` — open Browser, navigate to `index.html`, call `b.screenshot()`, assert the result is `bytes`, non-empty, and starts with `b'\x89PNG\r\n\x1a\n'`.
  - `test_screenshot_after_exit_raises_browser_closed` — exit the `with` block, then call `b.screenshot()`, assert `BrowserClosed` is raised.
  - `test_screenshot_full_page_is_at_least_viewport_sized` — navigate to a tall fixture (or set viewport small via `b._page.set_viewport_size(...)`), call both `b.screenshot()` and `b.screenshot(full_page=True)`, assert `len(full) >= len(viewport)`.
- [x] 2.2 Add the coordinate-click tests to `task2/tests/agent/test_browser.py`:
  - `test_click_at_fires_document_click_handler` — navigate to a fixture (can be `locate_l4_no_metadata.html` from step 1.1, or a small purpose-built fixture), call `b.click_at(150, 250)`, assert `b._page.evaluate("() => window.__l4_click")` returns `{"x": 150, "y": 250, "target": ...}`.
  - `test_click_at_inside_target_fires_target_handler` — same fixture, call `b.click_at(140, 220)`, assert the readback dict's `target` field equals `"target"` (the id of the painted div).
  - `test_click_at_after_exit_raises_browser_closed` — exit the `with` block, then call `b.click_at(10, 20)`, assert `BrowserClosed` is raised.
- [x] 2.3 From `task2/`, run `uv run pytest tests/agent/test_browser.py -x` and confirm the new tests fail with `AttributeError: 'Browser' object has no attribute 'screenshot'` (or `click_at`). Existing browser tests SHALL still pass.

## 3. Browser tool surface — implementation (green)

- [x] 3.1 In `task2/agent/browser.py`, add `def screenshot(self, *, full_page: bool = False) -> bytes:` after `read`. The body: `if self._page is None: raise BrowserClosed()` then `return self._page.screenshot(full_page=full_page)`.
- [x] 3.2 In `task2/agent/browser.py`, add `def click_at(self, x: int, y: int) -> None:` after `screenshot`. The body: `if self._page is None: raise BrowserClosed()` then `self._page.mouse.click(x, y)`.
- [x] 3.3 From `task2/`, run `uv run pytest tests/agent/test_browser.py` — all browser tests (existing + new) SHALL pass.

## 4. L4 vision — failing tests (red)

- [x] 4.1 Add `task2/tests/agent/test_locate_l4.py`. Import `locate, locate_l1, locate_l2, locate_l3, locate_l4, LocateResult, LocatorMiss` from `agent.locate` so the import alone fails until `locate_l4` exists. Also import `ChatResponse, Usage, LLMError` from `agent.llm`.
- [x] 4.2 Reuse the `_make_chat_stub` helper pattern from `test_locate_l3.py` — a callable conforming to `agent.llm.chat`'s signature, returning a `ChatResponse(content=..., tool_calls=[], finish_reason="stop", model="stub", usage=Usage(0,0,0), raw={})`. Add `_make_chat_stub_raising(exc)` that raises `exc` when invoked, and `_make_recording_chat_stub(content)` that captures the `messages` argument for inspection and returns the configured response.
- [x] 4.3 Write `test_locate_l4_happy_path_clicks_target_center` against `locate_l4_no_metadata.html`:
  - Open Browser, navigate, set viewport to `1280×800` (or whatever the conftest default is — record it).
  - Stub returns `{"bbox": [100, 200, 80, 40]}`.
  - Call `result = locate_l4(b._page, role="button", name=None, intent="Submit button", llm_chat=stub)`.
  - Assert `result.tier == "L4_vision"`, `result.confidence == 0.5`, `result.coords == (140, 220)`, `result.selector == ""`, `result.ax_fingerprint` is non-empty.
  - Then act on the result: `b.click_at(*result.coords)`.
  - Assert `b._page.evaluate("() => window.__l4_click")` reads back `{"x": 140, "y": 220, "target": "target"}` — proves the bbox center landed on the painted target.
- [x] 4.4 Write `test_locate_l4_malformed_json_raises_vision_miss` — same fixture, stub returns `content="not even close to JSON"`. Assert `LocatorMiss(reason="vision_miss", match_count=0)`.
- [x] 4.5 Write `test_locate_l4_missing_bbox_field_raises_vision_miss` — stub returns `{"box": [10, 20, 30, 40]}` (wrong key). Assert `vision_miss`.
- [x] 4.6 Write `test_locate_l4_wrong_arity_raises_vision_miss` — stub returns `{"bbox": [10, 20, 30]}`. Assert `vision_miss`.
- [x] 4.7 Write `test_locate_l4_zero_width_raises_vision_miss` — stub returns `{"bbox": [10, 20, 0, 40]}`. Assert `vision_miss`.
- [x] 4.8 Write `test_locate_l4_zero_height_raises_vision_miss` — stub returns `{"bbox": [10, 20, 30, 0]}`. Assert `vision_miss`.
- [x] 4.9 Write `test_locate_l4_negative_origin_raises_vision_miss` — stub returns `{"bbox": [-1, 20, 30, 40]}`. Assert `vision_miss`.
- [x] 4.10 Write `test_locate_l4_out_of_viewport_raises_vision_miss` — set viewport to `1280×800`, stub returns `{"bbox": [1200, 750, 200, 200]}`. Assert `vision_miss`.
- [x] 4.11 Write `test_locate_l4_non_numeric_bbox_raises_vision_miss` — stub returns `{"bbox": ["10", 20, 30, 40]}`. Assert `vision_miss`. (Documents that string-formatted numerics are rejected; `bool`s are also rejected.)
- [x] 4.12 Write `test_locate_l4_nan_bbox_raises_vision_miss` — stub returns content built from a Python dict with `float("nan")` serialized through `json.dumps` (which produces `NaN` — not strict JSON, so this also exercises the parse failure path; confirm by `json.loads('{"bbox": [NaN, 20, 30, 40]}')` raising). Assert `vision_miss`.
- [x] 4.13 Write `test_locate_l4_float_bbox_is_rounded` — stub returns `{"bbox": [99.6, 200.4, 80.0, 40.0]}`. Assert `result.coords == (140, 220)`.
- [x] 4.14 Write `test_locate_l4_llm_transport_error_raises_vision_miss` — stub raises `LLMError("transport boom", kind="transport")`. Assert `LocatorMiss(reason="vision_miss", match_count=0)`. Assert that `exc.__cause__` is the original `LLMError`.
- [x] 4.15 Write `test_locate_l4_prompt_shape_carries_image_data_url` — recording stub captures the `messages` list and returns a valid bbox. Assertions:
  - `len(messages) == 2`.
  - `messages[0]["role"] == "system"` and `"bbox" in messages[0]["content"]`.
  - `messages[1]["role"] == "user"` and `isinstance(messages[1]["content"], list)`.
  - The user content list contains exactly one `{"type": "text", ...}` entry whose `text` includes the substring `"Submit button"`.
  - The user content list contains exactly one `{"type": "image_url", ...}` entry whose `image_url.url` starts with `"data:image/png;base64,"`.
  - Decoding the base64 portion yields bytes that begin with the PNG signature `b'\x89PNG\r\n\x1a\n'`.
- [x] 4.16 Write `test_locate_l4_viewport_size_none_raises_vision_miss_without_calling_llm` — monkeypatch `b._page.viewport_size` (or a wrapper) to return `None`; pass a `fail_if_called` stub. Assert `LocatorMiss(reason="vision_miss")` is raised and the stub was never invoked. (If monkeypatching `viewport_size` directly is awkward in Playwright, this test can use `unittest.mock.patch.object` on the page object; document the choice in a comment.)
- [x] 4.17 Write `test_locate_l4_fingerprint_stable_for_same_intent_and_center` — call `locate_l4` twice with the same intent and same stub bbox; assert the two `LocateResult.ax_fingerprint` values are equal.
- [x] 4.18 Write `test_locate_l4_fingerprint_changes_with_center` — call `locate_l4` twice with the same intent but stubs returning two different in-bounds bboxes whose centers differ; assert the two fingerprints differ.
- [x] 4.19 Write `test_locate_orchestrator_cascades_l1_zero_l2_miss_to_l4` against `locate_l4_no_metadata.html`:
  - Stub returns a valid bbox.
  - Call `result = locate(b._page, "Submit button", llm_chat=stub)`.
  - Assert `result.tier == "L4_vision"` (L1 zero → L2 zero → L4 happy).
- [x] 4.20 Write `test_locate_orchestrator_cascades_l1_ambiguous_l3_malformed_to_l4` against `locate_l3_three_save.html`:
  - Stub is dispatch-aware: when the `messages` look like the L3 rerank prompt (text-only, mentions "rerank"/"index"), return malformed JSON; when they look like the L4 vision prompt (multimodal, has image_url), return a valid bbox.
  - Call `result = locate(b._page, "Save button", llm_chat=stub)`.
  - Assert `result.tier == "L4_vision"`.
- [x] 4.21 Write `test_locate_orchestrator_l1_success_does_not_invoke_llm` against `locate_l1.html` (existing fixture with one `<button>Submit</button>`):
  - Stub is `fail_if_called`.
  - Call `result = locate(b._page, "Submit button", llm_chat=stub)`.
  - Assert `result.tier == "L1_ax"` and stub was never invoked.
- [x] 4.22 Write `test_locate_orchestrator_intent_parse_error_does_not_invoke_llm`:
  - Stub is `fail_if_called`.
  - Call `locate(b._page, "do the thing", llm_chat=stub)`.
  - Assert `IntentParseError` is raised and the stub was never invoked.
- [x] 4.23 Write `test_locate_orchestrator_surfaces_vision_miss_when_all_tiers_fail`:
  - Use `locate_l4_no_metadata.html`.
  - Stub returns malformed JSON (so L4 also fails).
  - Call `locate(b._page, "Submit button", llm_chat=stub)`.
  - Assert `LocatorMiss(reason="vision_miss", match_count=0)`.
- [x] 4.24 Write `test_locate_l4_default_chat_honors_llm_base_url` — a unit-style test (no Playwright) that:
  - Monkeypatches `os.environ["LLM_BASE_URL"]` to `"http://vision.example.test"`.
  - Uses `pytest-httpx` (or `httpx.MockTransport` if `pytest-httpx` is not on the dev deps — confirm by checking `task2/pyproject.toml` `[tool.uv.dev-dependencies]`; if absent, add it via `uv add --dev pytest-httpx`) to capture the outbound request.
  - Calls `locate_l4(...)` with `llm_chat=None` (default-resolution path) using a minimal Playwright page (or stubs `page.viewport_size` and `page.screenshot()` directly to avoid Playwright dependence).
  - Asserts the captured request URL begins with `"http://vision.example.test/v1/chat/completions"`.
  - **Implementation note for the apply step**: this test will likely require a thin seam — if `locate_l4` builds a fresh `LLMClient` internally on the default path, the test must arrange a mock transport for that client. Easiest path: have `_resolve_default_llm_chat` return `agent.llm.chat` (the module-level function), which in turn constructs an `LLMClient` whose `_client` is `httpx.Client(timeout=...)`. Patch `httpx.Client` (or use the existing `agent.llm` test pattern) to capture URL.
- [x] 4.25 Update `task2/tests/agent/test_locate_l3.py::test_locate_orchestrator_surfaces_l3_ambiguous` — the assertion that `locate(...)` raises `LocatorMiss(reason="ambiguous")` is no longer correct (L3 ambiguous now cascades to L4). Either rename to `test_locate_orchestrator_l3_ambiguous_now_cascades_to_l4` and update the assertion to expect an L4 result (when the stub returns a valid L4 bbox) OR an L4 `vision_miss` (when the stub returns malformed for L4 too), OR delete it as redundant with the new cascade tests in step 4.20 / 4.23. Document the rename in the commit message.
- [x] 4.26 Update `task2/tests/agent/test_locate.py` and `tests/agent/test_locate_l2.py` — search for any test asserting that `locate()` raises `LocatorMiss(reason="zero_matches")` after L1+L2 miss. Those tests must now pass an `llm_chat` stub and either assert L4 success (if the stub returns a valid bbox) or L4 `vision_miss` (if the stub returns malformed). Pick the simplest assertion per test.
- [x] 4.27 From `task2/`, run `uv run pytest tests/agent/test_locate_l4.py -x` and confirm every test fails for the expected reason (missing `locate_l4` symbol, missing `coords` field on `LocateResult`, orchestrator not yet cascading to L4, missing `vision_miss` reason). Run `uv run pytest tests/agent/` and confirm the renamed/updated L2/L3 tests fail in the new expected way (cascade to L4 not yet wired).

## 5. L4 vision — implementation (green)

- [x] 5.1 In `task2/agent/locate.py`, extend `LocatorMissReason` literal: `LocatorMissReason = Literal["zero_matches", "ambiguous", "vision_miss"]`. The `_VALID_REASONS = frozenset(get_args(LocatorMissReason))` line will pick up the new value automatically.
- [x] 5.2 In `task2/agent/locate.py`, extend the `LocateResult` dataclass with `coords: tuple[int, int] | None = None` as the last field. Confirm the `frozen=True` decorator and existing field order are preserved (the new field is added at the end so existing positional construction sites do not break).
- [x] 5.3 Add module constants: `_L4_CONFIDENCE = 0.5`, `_L4_DATA_URL_PREFIX = "data:image/png;base64,"`.
- [x] 5.4 Add a private helper `_resolve_default_llm_chat()` (if not already present from ticket #5 — verify and DRY if duplicated) that does `from agent.llm import chat; return chat`.
- [x] 5.5 Add `_build_l4_messages(intent: str, viewport: tuple[int, int], png_b64: str) -> list[dict]`:
  - System message: `"You are a UI element localizer. Given a screenshot and an intent, return a single bounding box around the target element. Reply with EXACTLY the JSON object {\"bbox\": [x, y, w, h]} where x,y is the top-left corner in pixels (relative to the screenshot), and w,h are width and height in pixels. Do not wrap the JSON in code fences. Do not include any prose."`.
  - User message with list-shaped content: `[{"type": "text", "text": f"Intent: {intent}\nViewport: {vw}x{vh}"}, {"type": "image_url", "image_url": {"url": f"{_L4_DATA_URL_PREFIX}{png_b64}"}}]`.
- [x] 5.6 Add `_parse_l4_bbox(response, viewport_w, viewport_h) -> tuple[int, int]`:
  - `content = getattr(response, "content", None)`; if not `str`, return `None` sentinel (or raise an internal `ValueError` we then map to `vision_miss`).
  - `data = json.loads(content)`; on `ValueError`, signal failure.
  - Require `isinstance(data, dict)`, `"bbox" in data`, `isinstance(data["bbox"], (list, tuple))`, `len(data["bbox"]) == 4`.
  - For each component: reject `bool` and non-numeric (int/float) types; reject `NaN`/`inf` via `math.isfinite`.
  - Normalize: `int(round(v))` for each.
  - Validate bounds: `x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= viewport_w and y + h <= viewport_h`.
  - Return `(x + w // 2, y + h // 2)` on success.
- [x] 5.7 Implement `locate_l4(page, *, role, name, intent, llm_chat=None) -> LocateResult`:
  - Read viewport: `vp = page.viewport_size`; if `vp is None`, raise `LocatorMiss(reason="vision_miss", match_count=0)` immediately.
  - `png_bytes = page.screenshot(full_page=False)`; `png_b64 = base64.b64encode(png_bytes).decode("ascii")`.
  - Resolve `chat_fn = llm_chat if llm_chat is not None else _resolve_default_llm_chat()`.
  - `messages = _build_l4_messages(intent, (vp["width"], vp["height"]), png_b64)`.
  - `try: response = chat_fn(messages=messages, temperature=0.0)` `except LLMError as exc: raise LocatorMiss(reason="vision_miss", match_count=0) from exc`. (Lazy-import `LLMError` from `agent.llm`.)
  - Parse: try `_parse_l4_bbox(response, vp["width"], vp["height"])`. On any failure (parse, validation), `raise LocatorMiss(reason="vision_miss", match_count=0)`. On success, unpack `(cx, cy)`.
  - Compute fingerprint: `fingerprint = hashlib.sha256(f"vision:{intent}:{cx}:{cy}".encode()).hexdigest()`.
  - Return `LocateResult(tier="L4_vision", role=role, name=name, selector="", ax_fingerprint=fingerprint, confidence=_L4_CONFIDENCE, coords=(cx, cy))`.
- [x] 5.8 Modify `locate(page, intent, *, llm_chat=None)` to extend the cascade:
  ```python
  def locate(page, intent, *, llm_chat=None):
      role, name = parse_intent(intent)
      try:
          return locate_l1(page, role=role, name=name)
      except LocatorMiss as miss:
          if miss.reason == "zero_matches":
              try:
                  return locate_l2(page, role=role, name=name)
              except LocatorMiss:
                  return locate_l4(page, role=role, name=name, intent=intent, llm_chat=llm_chat)
          if miss.reason == "ambiguous":
              try:
                  return locate_l3(page, role=role, name=name, llm_chat=llm_chat)
              except LocatorMiss:
                  return locate_l4(page, role=role, name=name, intent=intent, llm_chat=llm_chat)
          raise
  ```
  Both L2's and L3's `LocatorMiss` (any reason) now cascades to L4. `IntentParseError` continues to propagate without invoking L4.
- [x] 5.9 Add `import base64` and `import math` (for `math.isfinite`) to the top of `agent/locate.py`. Confirm `agent.llm` is still NOT imported at module top (it must remain lazy in `_resolve_default_llm_chat` and in the `LLMError` catch inside `locate_l4`).
- [x] 5.10 From `task2/`, run `uv run pytest tests/agent/test_locate_l4.py` and confirm all new tests pass.
- [x] 5.11 From `task2/`, run `uv run pytest` (full suite). Confirm tickets #1–#5 tests still pass — in particular the renamed/updated tests in `test_locate.py`, `test_locate_l2.py`, and `test_locate_l3.py` reflect the new orchestrator behaviour, and L1/L2/L3 happy-path tests are unaffected.

## 6. Refactor + housekeeping

- [ ] 6.1 Reread `task2/agent/locate.py`. Look for opportunities to factor common helpers:
  - The `_resolve_default_llm_chat` helper, if it exists in two places now (for L3 and L4), should be a single private function.
  - `_build_l3_messages` and `_build_l4_messages` are intentionally separate — do NOT merge them, but confirm both follow the same `[{system}, {user}]` shape.
- [ ] 6.2 Reread `task2/agent/browser.py`. Confirm `screenshot` and `click_at` are placed alongside `read` (between `read` and the closing of the class), with consistent docstring style (matching `goto` / `read` if any).
- [ ] 6.3 Confirm `LocateResult`'s field order is `tier, role, name, selector, ax_fingerprint, confidence, coords` and the dataclass remains `frozen=True`.
- [ ] 6.4 Confirm `agent.llm` is NOT imported at module top of `agent.locate` (verify by reading the import block; the `LLMError` catch in `locate_l4` MUST be inside the function body, lazy-imported).
- [ ] 6.5 Run `uv run ruff format .` from `task2/` (no changes after green).
- [ ] 6.6 Run `uv run ruff check .` from `task2/` — clean.
- [ ] 6.7 No new runtime dependencies added to `task2/pyproject.toml`. The only allowed dev-dependency addition is `pytest-httpx` if step 4.24 requires it AND it is not already present.

## 7. Validation

- [ ] 7.1 Run `openspec validate implement-locate-l4 --strict` — change SHALL be valid.
- [ ] 7.2 Final pre-commit gate from `task2/`: `uv run ruff format .` (no changes), `uv run ruff check .` (clean), `uv run pytest` (all tests pass).
- [ ] 7.3 Three or four conventional commits on the branch:
  - `chore(task2): scaffold implement-locate-l4` (created in scaffolding step — counts).
  - `feat(task2): add screenshot and click_at to Browser`.
  - `test(task2): add failing L4 vision-locator tests and fixture`.
  - `feat(task2): add L4 vision-fallback locator tier and last-tier cascade`.
  - `refactor(task2): <whatever 6.1 ends up doing>` — only if a real cleanup happens; skip if nothing worth changing.
- [ ] 7.4 No hooks bypassed at any point. No `--no-verify` flags used.
