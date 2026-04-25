## Why

Tickets #3, #4, and #5 landed L1 (accessibility-tree), L2 (DOM heuristics), and L3 (LLM rerank over AX-tree candidates) in `agent/locate.py`. Every tier so far depends on *some* DOM/AX signal: a role+name match, a placeholder, a label-for, or an enumerable set of role-named candidates the LLM can pick among. Real sites routinely paint affordances as bare `<div>`s or background-image-only nodes — no role, no accessible name, no label, no placeholder, nothing for L1/L2/L3 to grip on. Today such targets resolve to `LocatorMiss` and the agent stalls. Ticket #6 adds the **L4 vision-fallback tier**: when L1–L3 all miss, capture a viewport screenshot, ask a vision LLM for the target's bounding box, and click the bbox center via Playwright's coordinate mouse API.

Per `task2/plan.md` line 246:

> **`locate.py` L4** — fixture where target has no accessible metadata; vision LLM mock returns a bbox; click hits expected coords.

## What Changes

- Extend `task2/agent/locate.py` with:
  - `locate_l4(page, *, role, name, intent, llm_chat=None) -> LocateResult` — vision-fallback tier. Captures a PNG screenshot of the current viewport via `page.screenshot(...)`, encodes it as a base64 `data:image/png;base64,...` URL, and sends a single OpenAI-compatible chat-completion to a vision-capable LLM with a `system` prompt instructing JSON-only reply of the form `{"bbox": [x, y, w, h]}` (pixels, viewport-relative) and a multimodal `user` message carrying the intent text and the image URL. Parses the reply, validates the bbox (in-bounds against the viewport, `w > 0`, `h > 0`), computes the center `(cx, cy) = (x + w/2, y + h/2)`, and returns a `LocateResult(tier="L4_vision", confidence=0.5)` whose action target is the coordinate pair. If the reply is malformed, the bbox is out of bounds, or the LLM call errors, `locate_l4` SHALL raise `LocatorMiss(reason="vision_miss", match_count=0)` — a new typed reason.
  - Extend the `LocateResult` dataclass to carry coordinate output for the L4 case. The L1/L2/L3 fields (`role`, `name`, `selector`, `ax_fingerprint`, `confidence`, `tier`) remain. A new optional field `coords: tuple[int, int] | None = None` is added; tiers L1/L2/L3 leave it `None`, and L4 populates it with the bbox center. The `selector` field on an L4 result SHALL be the empty string (or a sentinel `"l4_vision_coords"`); the `ax_fingerprint` SHALL be `sha256(f"vision:{intent}:{cx}:{cy}".encode()).hexdigest()` so the cache layer (ticket #7) can distinguish L4 hits from selector-based hits.
  - Extend `locate(page, intent, *, llm_chat=None)` so an L3 `LocatorMiss` (regardless of reason) AND an L2 `LocatorMiss(reason="zero_matches")` cascade into `locate_l4(page, role=role, name=name, intent=intent, llm_chat=llm_chat)`. The existing L1 → L2 (zero) and L1 → L3 (ambiguous) cascades are preserved; L4 sits as the last-chance tier under both. If L4 also misses, `locate()` SHALL raise the L4 `LocatorMiss(reason="vision_miss", match_count=0)`.
  - Add the per-tier confidence value `0.5` for L4, slotting below L2 (`0.7`).
  - Add `LocatorMissReason` value `"vision_miss"` to the existing `Literal` type so existing typing remains exhaustive.
- Extend `task2/agent/browser.py` with:
  - A coordinate-based `click_at(x, y)` method that invokes `page.mouse.click(x, y)` after asserting the page is open. Required because the existing `Browser` exposes no coordinate-click API — only selector-based `read`. L4's act path uses this method.
  - A `screenshot(*, full_page=False) -> bytes` method that returns raw PNG bytes from `page.screenshot(...)`. Required because the existing `Browser` exposes no screenshot capture. `locate_l4` consumes the bytes directly.
- Add `task2/tests/fixtures/locate_l4_no_metadata.html`: a single clickable target rendered as a `<div>` with no role, name, label, placeholder, or text content (e.g. an icon-only button represented by a CSS background image), styled at known pixel coordinates so a bbox center deterministically falls on it. The target SHALL register a JS click handler that sets `window.__l4_clicked = {x, y}` so tests can read back exactly where the click landed.
- Add `task2/tests/agent/test_locate_l4.py` covering: happy-path bbox-center click hits the target; malformed JSON reply → `LocatorMiss(reason="vision_miss")`; missing `bbox` field → `LocatorMiss`; bbox with non-positive width/height → `LocatorMiss`; bbox out of viewport bounds → `LocatorMiss`; LLM transport error → `LocatorMiss(reason="vision_miss")`; orchestrator cascade L1 zero → L2 zero → L4 (skips L3 since L3 only fires on ambiguous); orchestrator cascade L1 ambiguous → L3 ambiguous → L4; orchestrator skips L4 entirely when L1 succeeds (assert vision LLM stub is not invoked); vision LLM client honors `LLM_BASE_URL` (a small unit test that the default-resolved L4 client posts to the configured base URL — same pattern as ticket #1).

Out of scope: locator cache (ticket #7) — though the ticket #6 spec leaves an `ax_fingerprint` on L4 results so the cache can later read/write them. Supervisor escalation (ticket #8). Browser tool surface beyond `screenshot` and `click_at`. Choosing between hosted vision providers — the LLM client honors `LLM_BASE_URL` like every other tier; running against a non-vision endpoint will surface as `vision_miss` at runtime but is not the test's contract.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `locator-pipeline`: extend the entry point and add the L4 tier. New requirements:
  - **L4 vision-fallback resolution** (vision LLM picks a bbox; locator returns a coordinate target).
  - Updated **Locator pipeline entry point** behavior: `locate()` cascades L2 `zero_matches` → L4 and L3 `*` → L4 in addition to the existing cascades.
  - Updated **`LocateResult` shape**: a new optional `coords` field carries an `(x, y)` pixel pair for L4 hits.
  - New **vision LLM request contract**: the L4 prompt is OpenAI-compatible chat-completions with a multimodal user message containing a `data:image/png;base64,...` image URL; the response contract is JSON-only `{"bbox": [x, y, w, h]}`.
- `browser-tools`: extend `agent/browser.py` with `screenshot()` and `click_at(x, y)` methods. (If no `browser-tools` spec exists yet under `openspec/specs/`, this is added as a new capability spec under the same change.)

## Impact

- **Code**: `task2/agent/locate.py` (new `locate_l4`, modified `locate`, extended `LocateResult` and `LocatorMissReason`); `task2/agent/browser.py` (new `screenshot`, `click_at`); new tests `task2/tests/agent/test_locate_l4.py`; one new fixture `task2/tests/fixtures/locate_l4_no_metadata.html`.
- **Dependencies**: none new. `agent.llm.chat` already supports OpenAI-compatible multimodal `messages` (the request body is passed through verbatim — multimodal content is just a list-shaped `content` field on a user message). No new HTTP client, no PIL/imaging libs (the screenshot is opaque PNG bytes; base64 encoding via `base64.b64encode` is stdlib).
- **Existing modules**: `agent/llm.py` unchanged. L1/L2/L3 paths are unchanged; only the orchestrator's recovery on L2 `zero_matches` and L3 misses changes (both now cascade to L4 instead of propagating). Existing tests that asserted "L2 zero_matches propagates" or "L3 ambiguous propagates" must be updated to reflect the new last-tier behaviour.
- **Deployment**: no Zeabur impact — the agent loop is not yet wired up, so production traffic does not reach `locate_l4` in this ticket. The vision LLM endpoint must be reachable from wherever the deployed agent runs; same `LLM_BASE_URL` env wiring as every other tier.
