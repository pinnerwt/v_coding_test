## Context

`task2/agent/locate.py` after ticket #5 cascades L1 → (L2 on zero / L3 on ambiguous). L2 still propagates `LocatorMiss` directly to the caller; L3 propagates `LocatorMiss(reason="ambiguous")` when the LLM cannot disambiguate. Both terminate the resolve attempt without using vision. The driver case from `task2/plan.md` ticket #6 is "fixture where target has no accessible metadata; vision LLM mock returns a bbox; click hits expected coords." A bare `<div>` with a CSS background image has no role, no name, no label, no placeholder, no role-named candidates — every L1/L2/L3 path returns `zero_matches`. Vision is the only signal left.

The constraints are the same as prior tiers, with two new shapes:

1. **The locator API has been selector-only.** L1/L2/L3 each return a Playwright-resolvable selector string. L4 cannot — there is no DOM node we can name. The output is a coordinate pair, and the action site (currently `agent/browser.py` for the test path; later `agent/loop.py` for the agent path) must learn to click coordinates instead of selectors. The `LocateResult` dataclass therefore grows a new optional `coords` field rather than overloading `selector`.
2. **The LLM call is multimodal.** L3's chat-completions request was text-only. L4's user message has a list-shaped `content` carrying both a text part (the intent + bbox-format instruction) and an `image_url` part with a `data:image/png;base64,...` URL. `agent/llm.py`'s `LLMClient.chat` passes `messages` through verbatim to the OpenAI-compatible endpoint, so this is a contract with the *server*, not a code change in the client. Tests stub `llm_chat` directly, so the wire format is exercised end-to-end only on the deployed path; the test path asserts the prompt assembly and response parsing.

Constraints inherited from prior tickets:

- **Tests use real Playwright; the LLM is mocked.** Same rule as #1–#5. The vision LLM is a stub returning a deterministic bbox.
- **No new dependency.** Stdlib `base64` for encoding; Playwright already exposes `page.screenshot(...)` and `page.mouse.click(x, y)`.
- **No hardcoded LLM provider.** The L4 vision call goes through `agent.llm.chat` (or the injected `llm_chat`), which already honors `LLM_BASE_URL`. There is no separate "vision client" — the same chat-completions endpoint is asked to handle multimodal input. The deployed Zeabur instance points `LLM_BASE_URL` at whatever vision-capable endpoint the operator has stood up.
- **Confidence ordering preserved.** L1=1.0, L2=0.7, L3=0.8, L4=0.5. L4 sits below all selector-based tiers because a vision pick is the least precise: a bbox center can land on an overlay, a tooltip, an adjacent control. It is still better than nothing.

## Goals / Non-Goals

**Goals:**
- A `locate_l4(page, *, role, name, intent, llm_chat=None) -> LocateResult` resolver that:
  - Captures the current viewport screenshot (PNG bytes) via `page.screenshot(full_page=False)`.
  - Reads the viewport size via `page.viewport_size` (returns a `{width, height}` dict from Playwright). Falls back to `(0, 0)` only if Playwright returns `None`, in which case `locate_l4` SHALL raise `LocatorMiss(reason="vision_miss", match_count=0)` immediately (no LLM call).
  - Builds an OpenAI-compatible chat-completion `messages` list with a system prompt instructing strict JSON-only reply `{"bbox": [x, y, w, h]}` (pixels, viewport-relative, integers preferred but floats accepted) and a user message whose `content` is a 2-element list: `{"type": "text", "text": <intent + viewport size>}` and `{"type": "image_url", "image_url": {"url": "data:image/png;base64,<b64>"}}`.
  - Invokes `llm_chat(messages=..., temperature=0.0)`; on any `LLMError` from `agent.llm`, raises `LocatorMiss(reason="vision_miss", match_count=0)`.
  - Parses the response. Validation rules: `response.content` MUST `json.loads` to a dict; the dict MUST have a `bbox` key whose value is a list of exactly 4 numbers; each number MUST be a finite (no NaN/inf) numeric, normalized to `int` via `int(round(v))`; resulting `(x, y, w, h)` MUST satisfy `0 <= x < viewport_w`, `0 <= y < viewport_h`, `w > 0`, `h > 0`, `x + w <= viewport_w`, `y + h <= viewport_h`. Any failure → `LocatorMiss(reason="vision_miss", match_count=0)`.
  - Computes the click target as `cx = x + w // 2`, `cy = y + h // 2`.
  - Returns `LocateResult(tier="L4_vision", role=role, name=name, selector="", ax_fingerprint=sha256(f"vision:{intent}:{cx}:{cy}".encode()).hexdigest(), confidence=0.5, coords=(cx, cy))`.
- An updated `locate(page, intent, *, llm_chat=None)` whose error-recovery cascade is:
  - L1 success → return.
  - L1 `zero_matches` → L2; if L2 succeeds, return.
  - L1 `ambiguous` → L3; if L3 succeeds, return.
  - L2 `LocatorMiss` (any reason) → L4.
  - L3 `LocatorMiss` (any reason) → L4.
  - L4 success → return; L4 `LocatorMiss` propagates.
- A `LocateResult` shape extended with `coords: tuple[int, int] | None = None` (default `None` for L1/L2/L3; populated for L4).
- A new `LocatorMissReason` value `"vision_miss"`.
- `agent/browser.py` extended with `screenshot()` and `click_at(x, y)` so tests (and later the agent loop) can drive the L4 act path.

**Non-Goals:**
- Locator cache (ticket #7). The `ax_fingerprint` on L4 results is shaped to be cache-compatible, but no read/write happens here.
- Supervisor-level policy: budget, repeated-attempt backoff, alternative strategies (ticket #8).
- Wiring `locate_l4` into the agent loop's tool dispatch (ticket #9).
- Cross-tier prompt sharing. L4's prompt is bespoke and lives next to `locate_l4`; we do not factor a "rerank/vision prompt builder" out yet.
- Multi-bbox or top-k vision responses. The LLM returns one bbox; if it returns multiple we treat the response as malformed.
- Scrolling to bring an off-viewport target into view. The current viewport is the search space; off-viewport targets are an L5 / pre-locate concern.
- Image preprocessing (cropping, downscaling, annotations). The raw `page.screenshot()` PNG is sent as-is.
- Choosing a vision model. The deployed `LLM_MODEL` env determines whether the configured endpoint is vision-capable; tests do not exercise that path.

## Decisions

### Extend `LocateResult` with a `coords` field, do not overload `selector`

Alternatives considered:
- **Encode coords into the selector string** (e.g. `coords=10,20`). Rejected — `page.locator(selector)` would not understand it, callers would need to switch on the string format, and the type contract becomes "selector is sometimes a selector and sometimes a coord pair." Type-fragile.
- **Subclass `LocateResult` into `SelectorLocateResult` and `CoordLocateResult`.** Rejected — every existing caller (and every test) treats `LocateResult` as a single concrete dataclass. Subclassing breaks `dataclass(frozen=True)` ergonomics and forces `isinstance` branches everywhere a result is consumed.
- **Add a discriminated union via a `kind` field.** Considered — but `tier` already discriminates (`L1_ax | L2_dom | L3_rerank | L4_vision`), so a separate `kind` would be redundant. Callers that want to act on the result branch on `tier` (or check `coords is not None`).

The chosen shape: one extra optional field, default `None`, populated only by L4.

```python
@dataclass(frozen=True)
class LocateResult:
    tier: str
    role: str
    name: str | None
    selector: str
    ax_fingerprint: str
    confidence: float
    coords: tuple[int, int] | None = None
```

### `LocatorMissReason = "vision_miss"` as a new typed reason

Alternatives:
- **Reuse `"zero_matches"`.** Rejected — the supervisor (ticket #8) wants to distinguish "L4 was reached and also failed" from "no DOM matches at L1." A vision miss is structurally a different failure mode (LLM didn't return a usable bbox) and the trace should record it as such.
- **Reuse `"ambiguous"`.** Rejected — same reasoning, and "ambiguous" implies multiple candidates, which is not what happens at L4.
- **Add `"llm_unparseable"`.** Considered — but the L3 design.md explicitly deferred that to ticket #8 and folded all L3 LLM-parse failures under `"ambiguous"`. To stay consistent with that decision, L4's parse/transport failures could fold under `"vision_miss"` as a single bucket. We pick `"vision_miss"` and document that all L4 failure modes (transport, malformed JSON, missing field, out-of-bounds bbox, non-positive dims) collapse into it. The trace event records the prompt/response verbatim so the operator can still see *which* sub-mode triggered.

### Cascade L2 zero AND L3 (any) into L4

The orchestrator after ticket #5:

```
L1 → on zero_matches → L2 (terminal)
L1 → on ambiguous   → L3 (terminal)
```

After ticket #6:

```
L1 → on zero_matches → L2 → on any miss → L4 (terminal)
L1 → on ambiguous   → L3 → on any miss → L4 (terminal)
```

Why "L3 on any miss" rather than "L3 on ambiguous only": if L3's LLM rerank cannot pick (malformed reply, out-of-range index), the system has already confirmed that the AX-tree candidates are present but the disambiguator failed. Vision may still pick correctly because it sees the rendered page, not just the AX tree. Sending an ambiguous L3 fall-through to L4 is therefore strictly more capable than dead-ending. Symmetric for L2 zero: vision sees pixels L2 cannot enumerate.

Why not "L1 ambiguous → L4 directly, skipping L3": L3 is cheaper than L4 (text-only LLM round-trip vs vision round-trip plus a screenshot capture round-trip). L3 first, L4 only if L3 also misses.

We deliberately do NOT cascade `IntentParseError` to L4 — an unparseable intent is a programmer/LLM-loop bug, not a UI-state failure, and L4 has no extra signal to apply.

### Vision prompt: strict JSON-only `{"bbox": [x, y, w, h]}`

Same rationale as L3's strict-JSON design (see archived ticket #5 design.md "LLM contract"). We avoid `tools=[...]` for the same reason — Qwen3.5-27B and most OpenAI-compatible local servers honour content-only JSON more reliably than `tools`. The system prompt:

```
You are a UI element localizer. Given a screenshot and an intent, return a single
bounding box around the target element. Reply with EXACTLY the JSON object
{"bbox": [x, y, w, h]} where x,y is the top-left corner in pixels (relative to
the screenshot), and w,h are width and height in pixels. Do not wrap the JSON in
code fences. Do not include any prose.
```

The user message:

```python
[
  {"type": "text", "text": f"Intent: {intent}\nViewport: {vw}x{vh}"},
  {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
]
```

Including the viewport size in the text prompt is belt-and-suspenders — most vision models infer it from the image, but stating it makes out-of-bounds responses easier to detect as "model hallucinated coordinates" rather than "model used a different scale."

### Bbox validation: hard pixel bounds, integer normalization

We accept `int` or `float` for each bbox component, but normalize via `int(round(v))` before bounds-checking. Rationale:
- Some models return floats (`[100.5, 200.0, 50.25, 30.75]`); rejecting them as "non-integer" would be needlessly fragile.
- We round half-to-even (Python default), then validate. A bbox that rounds out of bounds is rejected.
- `NaN` and `inf` short-circuit before rounding (a `NaN bbox` is malformed input, not a numeric edge case).

The bounds check is deliberately strict: `x + w` must be `<=` viewport width (inclusive of the right edge), not `<` it, since a target at the page's right edge is legitimate. Same for the bottom edge. `w > 0` and `h > 0` reject degenerate boxes; a zero-area box is a model failure, not a corner-case hit.

### Click target: bbox center via `page.mouse.click(cx, cy)`

Alternatives:
- **Click the bbox top-left.** Rejected — the top-left is the model's coordinate origin, not a meaningful click site (e.g. a button's hit-target is its center, not its corner).
- **Use `page.locator('xpath=//*').click({position: {x, y}})`.** Rejected — there is no element to anchor on; the entire premise of L4 is that no selector exists.
- **Use `page.click(selector, position=...)` with a synthetic body selector.** Considered — `page.locator('body').click(position={x: cx, y: cy})` works, but the offset is *relative to the body's bounding box*, which differs from viewport coordinates when the page has scrolled or has body margins. `page.mouse.click(x, y)` uses viewport coordinates directly, which matches what the vision model returned. Simpler.

`page.mouse.click(cx, cy)` does not move the mouse before clicking; we accept that. If a future test surfaces hover-dependent UI, we can add `page.mouse.move(cx, cy); page.mouse.click(cx, cy)` then.

### `ax_fingerprint` for L4: hash of intent + click center

```
fingerprint = sha256(f"vision:{intent}:{cx}:{cy}".encode()).hexdigest()
```

Reason: the cache (ticket #7) stores `(origin, intent) → ax_fingerprint`. Two L4 hits across runs that pick "the same target" produce the same `(cx, cy)` (up to model determinism at temperature 0) and therefore the same fingerprint. If the layout shifts and the target moves, the fingerprint changes and the cache invalidates — which is exactly the "fingerprint mismatch invalidates" behaviour ticket #7 requires.

We deliberately prefix with `"vision:"` so an L4 fingerprint never collides with an L1/L2/L3 fingerprint for the same `(role, name)`. The cache layer treats all four as opaque hashes and never inspects the prefix; the prefix is purely a defensive separation.

### Screenshot scope: viewport only, not full page

`page.screenshot(full_page=False)` captures only the visible viewport. Alternatives:
- **`full_page=True`** — captures the entire scrollable page. Rejected — the click happens at viewport coordinates; a bbox at `(y=4000)` on a full-page screenshot does not correspond to a viewport pixel without scrolling, and we explicitly exclude scrolling from L4's scope.
- **`clip={x, y, w, h}`** — could narrow to a known region. Rejected — we don't know where the target is until the model picks; the whole viewport is the search space.

### Browser tool surface: add `screenshot()` and `click_at(x, y)`, do not refactor existing methods

The existing `Browser.read(selector)` is selector-based; we leave it untouched. The two new methods are additive:

```python
def screenshot(self, *, full_page: bool = False) -> bytes:
    if self._page is None:
        raise BrowserClosed()
    return self._page.screenshot(full_page=full_page)

def click_at(self, x: int, y: int) -> None:
    if self._page is None:
        raise BrowserClosed()
    self._page.mouse.click(x, y)
```

We do NOT widen `Browser.click(intent)` (which doesn't exist yet) in this ticket — the agent-loop tool surface is a later ticket's concern. L4's tests directly call `b._page.mouse.click(...)` via the new `click_at` method (or via `b._page` for the click-handler-readback verification path).

### Lazy `agent.llm` import preserved

Same as L3: `locate_l4`'s default-resolver imports `agent.llm.chat` lazily so `import agent.locate` does not pull in `httpx` at module load. The two-line helper `_resolve_default_llm_chat()` from ticket #5 is reused.

### Module organization: keep L4 in `locate.py`

Same call as L1/L2/L3. After this change `locate.py` will be ~500 LoC. A future split (e.g. `locate/__init__.py` + per-tier files) may be warranted when L5 lands or when the cache (ticket #7) adds another ~150 LoC. Not yet.

## Assumptions

These assumptions were made because the existing code does not pin them; the apply step should confirm or correct.

1. **`LocateResult` does not yet have a `coords` field.** Verified by reading `task2/agent/locate.py` lines 97–104 — the dataclass currently has six fields and none are coordinate-typed. The change adds `coords: tuple[int, int] | None = None` as a new defaulted field at the end (preserving backwards compatibility for existing positional / keyword construction).
2. **`agent/browser.py` does not yet expose screenshot or coordinate-click methods.** Verified by reading the file — only `goto`, `read`, and the context-manager protocol are present. The change adds two new methods.
3. **`page.viewport_size` returns a `{"width": int, "height": int}` dict (or `None`).** Standard Playwright behaviour. If a future Playwright upgrade changes the shape, the parse is one line and easy to fix.
4. **The test fixture's click handler stores click coordinates, not just a "clicked" flag.** This lets the test assert the bbox center landed inside the target's painted area rather than just "some click happened." The fixture itself is in the test setup — see `tasks.md` step 1.1.
5. **The vision LLM stub returns a `ChatResponse` shaped like `agent.llm.ChatResponse`.** Tests construct `ChatResponse(content='{"bbox": [...]}', ...)` directly; they do not need to mimic the multimodal request shape because the stub is invoked at the Python boundary, not the HTTP boundary.
6. **`agent.llm.chat`'s message contract accepts list-shaped `content`.** Verified by reading `agent/llm.py` — the `messages: list[dict]` parameter is passed through to `httpx.post(..., json=body)` verbatim, so the OpenAI-compatible multimodal shape (`content: list[{type, ...}]`) is wire-compatible with the existing client. No client changes needed.

If any of (1)–(6) is wrong, the apply agent should call out the divergence and adjust the change before committing.

## Risks / Trade-offs

- **Vision LLM cost / latency.** Each L4 call ships a base64 PNG + LLM round-trip. On a typical 1280×800 viewport that's ~200KB-1MB of image data per request and several hundred ms of latency. → Mitigated by ticket #7's cache: a successful L4 result caches by `(origin, intent)` and the vision call is skipped on re-resolve. Until ticket #7 lands, L4 cost is per-attempt.
- **Vision model JSON discipline.** Same risk as L3, more pronounced — multimodal models are often noisier in their text output. A malformed reply degrades to `LocatorMiss(reason="vision_miss")`. → The eval set (ticket #15) measures real-world reliability; if it's too low we can constrain via `tools=[...]` or a stricter system prompt.
- **Bbox accuracy.** A model returning a bbox off-target by ~50px on a small button still validates as "in bounds" but clicks the wrong element (or empty space). The test fixture is designed to make this visible: the click handler reads back exact coordinates, so a near-miss is caught. The eval set will surface broader failure modes.
- **Confidence=0.5 is a magic number.** Same caveat as L2 (0.7) and L3 (0.8). The literal value is not load-bearing; the ordering is. Documented in the spec.
- **Viewport assumption.** L4 assumes the target is in the current viewport. Off-viewport targets fail with no useful diagnostic. → Out of scope for this ticket; a pre-locate "scroll to find" step is a separate future tier.
- **Coordinate stability under scroll.** If the page scrolls between screenshot capture and click execution, the coordinate becomes wrong. → The full sequence runs synchronously inside one Playwright tick; no awaited navigation happens between `screenshot()` and `click_at()`. Documented.
- **Mocking the LLM in tests.** Same trade-off as L3. Tests verify the L4 plumbing — prompt assembly, multimodal message shape, response parsing, bbox validation, click coordinate computation. They do NOT verify a real vision model can find buttons. The eval set is the test surface for that.
- **Browser API surface widened.** `Browser.click_at(x, y)` and `Browser.screenshot()` are now on the public surface. The two are intentionally minimal — no convenience wrappers, no JPEG/quality parameters — to keep the contract small. If the agent loop later needs richer screenshot options, those go in a follow-up ticket.

## Migration Plan

No data migration. No deployment migration. The change is additive at the API surface (`coords` field is defaulted; `locator-miss` reason is a new literal; new browser methods don't conflict). The only behaviour change for existing callers is "L2 / L3 misses no longer propagate; they cascade to L4." Two existing tests must be updated:
- `tests/agent/test_locate.py::test_locate_surfaces_l2_zero_matches` (or its equivalent) — must now assert L4 was invoked.
- `tests/agent/test_locate_l3.py::test_locate_orchestrator_surfaces_l3_ambiguous` — must now assert L4 was invoked.

The apply step's `tasks.md` calls these renames out explicitly.

## Open Questions

- Should L4 retry once on `LLMError(kind="transport")` before declaring `vision_miss`? Defer to ticket #8 supervisor — single-shot for now.
- Should the vision prompt include the *page URL* alongside the intent? It might help disambiguation on familiar sites. Defer; would bloat the prompt and is not on the test path.
- Should `LocateResult.selector` be `""` or a sentinel like `"l4_vision_coords"` for L4 hits? Picked `""` — callers that branch on `coords is not None` are already on the new path; a sentinel would be a second discriminator with no extra information.
