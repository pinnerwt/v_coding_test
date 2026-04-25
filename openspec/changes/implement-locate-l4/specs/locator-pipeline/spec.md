## ADDED Requirements

### Requirement: L4 vision-fallback resolution

The system SHALL provide `agent.locate.locate_l4(page, *, role, name, intent, llm_chat=None) -> LocateResult` that resolves an element by capturing a viewport screenshot, asking a vision-capable LLM to return a bounding box around the target, and returning a coordinate target rather than a DOM selector.

`locate_l4` SHALL:

1. Read the viewport size via `page.viewport_size`. If `viewport_size` is `None`, `locate_l4` SHALL raise `LocatorMiss(reason="vision_miss", match_count=0)` immediately, without invoking the LLM or capturing a screenshot.
2. Capture a viewport screenshot via `page.screenshot(full_page=False)` returning raw PNG bytes.
3. Encode the PNG bytes as a `data:image/png;base64,<b64>` URL via stdlib `base64.b64encode`.
4. Resolve the LLM callable: `chat_fn = llm_chat if llm_chat is not None else _resolve_default_llm_chat()`. The default-resolver SHALL import `agent.llm.chat` lazily so module load of `agent.locate` does not pull in `agent.llm` / `httpx`.
5. Build a two-message OpenAI-compatible chat-completions `messages` list:
   - A `system` message instructing strict JSON-only reply of the form `{"bbox": [x, y, w, h]}` where `x,y` is the top-left corner in pixels (relative to the screenshot) and `w,h` are the width and height in pixels; no code fences, no prose.
   - A `user` message whose `content` is a 2-element list: a `{"type": "text", "text": ...}` part containing the intent (e.g. `"Submit button"`) and the viewport size, and a `{"type": "image_url", "image_url": {"url": "data:image/png;base64,<b64>"}}` part.
6. Invoke `chat_fn(messages=messages, temperature=0.0)`. If the call raises `LLMError` (any kind: transport, http, decode, config), `locate_l4` SHALL raise `LocatorMiss(reason="vision_miss", match_count=0)` with the original error chained via `raise ... from`.
7. Parse the response:
   - `response.content` MUST `json.loads` to a `dict`.
   - The dict MUST have a `bbox` key whose value is a `list` (or `tuple`) of exactly 4 numeric items.
   - Each item MUST be a finite number (`int` or `float`, not `bool`, not `NaN`, not `inf`).
   - Each item is normalized to `int` via `int(round(v))`.
   - The resulting `(x, y, w, h)` MUST satisfy `x >= 0`, `y >= 0`, `w > 0`, `h > 0`, `x + w <= viewport_w`, `y + h <= viewport_h`.
   - Any failure SHALL raise `LocatorMiss(reason="vision_miss", match_count=0)`.
8. Compute the click target: `cx = x + w // 2`, `cy = y + h // 2`.
9. Return `LocateResult(tier="L4_vision", role=role, name=name, selector="", ax_fingerprint=sha256(f"vision:{intent}:{cx}:{cy}".encode()).hexdigest(), confidence=0.5, coords=(cx, cy))`.

`locate_l4` SHALL NOT be invoked by L1, L2, or L3; it is reachable directly or via `locate()`'s last-tier cascade.

#### Scenario: Vision LLM returns valid bbox; click center is computed and returned

- **GIVEN** a page exposing a target element rendered as a bare `<div>` with no role, no accessible name, no label, and no placeholder
- **AND** the target is painted at viewport pixel rect `(100, 200, 80, 40)` (x, y, w, h)
- **AND** a stub `llm_chat` that returns a `ChatResponse` whose `content` is exactly the JSON string `{"bbox": [100, 200, 80, 40]}`
- **WHEN** a caller invokes `locate_l4(page, role="button", name=None, intent="Submit button", llm_chat=stub)`
- **THEN** the call SHALL return a `LocateResult` with `tier == "L4_vision"`
- **AND** `result.confidence` SHALL equal `0.5`
- **AND** `result.coords` SHALL equal `(140, 220)`
- **AND** `result.selector` SHALL equal `""`
- **AND** `result.ax_fingerprint` SHALL be a non-empty string

#### Scenario: Malformed JSON reply raises vision_miss

- **GIVEN** a page with the same target as above
- **AND** a stub `llm_chat` that returns a `ChatResponse` whose `content` is the string `not even close to JSON`
- **WHEN** a caller invokes `locate_l4(page, role="button", name=None, intent="Submit button", llm_chat=stub)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"vision_miss"`
- **AND** `LocatorMiss.match_count` SHALL equal `0`

#### Scenario: Missing bbox field raises vision_miss

- **GIVEN** a page with a target
- **AND** a stub `llm_chat` returning `{"box": [10, 20, 30, 40]}` (wrong key name)
- **WHEN** a caller invokes `locate_l4(page, role="button", name=None, intent="Submit button", llm_chat=stub)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"vision_miss"`

#### Scenario: Bbox with non-positive dimensions raises vision_miss

- **GIVEN** a page with a target
- **AND** a stub `llm_chat` returning `{"bbox": [10, 20, 0, 40]}` (zero width)
- **WHEN** a caller invokes `locate_l4(page, role="button", name=None, intent="Submit button", llm_chat=stub)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"vision_miss"`

#### Scenario: Bbox out of viewport bounds raises vision_miss

- **GIVEN** a page with viewport `1280×800`
- **AND** a stub `llm_chat` returning `{"bbox": [1200, 750, 200, 200]}` (extends past right and bottom edges)
- **WHEN** a caller invokes `locate_l4(page, role="button", name=None, intent="Submit button", llm_chat=stub)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"vision_miss"`

#### Scenario: Negative bbox origin raises vision_miss

- **GIVEN** a page with a target
- **AND** a stub `llm_chat` returning `{"bbox": [-10, 20, 30, 40]}` (negative x)
- **WHEN** a caller invokes `locate_l4(page, role="button", name=None, intent="Submit button", llm_chat=stub)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"vision_miss"`

#### Scenario: Bbox with wrong arity raises vision_miss

- **GIVEN** a page with a target
- **AND** a stub `llm_chat` returning `{"bbox": [10, 20, 30]}` (only 3 numbers)
- **WHEN** a caller invokes `locate_l4(page, role="button", name=None, intent="Submit button", llm_chat=stub)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"vision_miss"`

#### Scenario: Float bbox coordinates are accepted and rounded

- **GIVEN** a page with a target painted at `(100, 200, 80, 40)`
- **AND** a stub `llm_chat` returning `{"bbox": [99.6, 200.4, 80.0, 40.0]}`
- **WHEN** a caller invokes `locate_l4(page, role="button", name=None, intent="Submit button", llm_chat=stub)`
- **THEN** the call SHALL return a `LocateResult` with `tier == "L4_vision"`
- **AND** `result.coords` SHALL equal `(140, 220)`

#### Scenario: LLM transport error is mapped to vision_miss

- **GIVEN** a page with a target
- **AND** a stub `llm_chat` that raises `agent.llm.LLMError("transport boom", kind="transport")` when invoked
- **WHEN** a caller invokes `locate_l4(page, role="button", name=None, intent="Submit button", llm_chat=stub)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"vision_miss"`
- **AND** the chained cause (`__cause__`) SHALL be the original `LLMError`

#### Scenario: Vision prompt carries the screenshot as a base64 data URL

- **GIVEN** a page with a target, viewport size known
- **AND** a recording stub `llm_chat` that captures the `messages` argument and returns a valid bbox
- **WHEN** a caller invokes `locate_l4(page, role="button", name=None, intent="Submit button", llm_chat=stub)`
- **THEN** the captured `messages` SHALL be a list of length `2`
- **AND** the first message SHALL have `role == "system"` and its `content` SHALL contain the substring `"bbox"`
- **AND** the second message SHALL have `role == "user"` and its `content` SHALL be a list
- **AND** that list SHALL contain exactly one element with `type == "text"` whose `text` contains the intent string `"Submit button"`
- **AND** that list SHALL contain exactly one element with `type == "image_url"` whose `image_url.url` starts with the prefix `"data:image/png;base64,"`

#### Scenario: AX fingerprint is deterministic for the same intent and click center

- **GIVEN** two runs of `locate_l4` against pages that produce the same intent and the same `(cx, cy)` click center
- **WHEN** both runs return successfully
- **THEN** the two `LocateResult.ax_fingerprint` values SHALL be equal

#### Scenario: AX fingerprint changes when click center changes

- **GIVEN** two runs of `locate_l4` with the same intent but different validated bbox centers
- **WHEN** both runs return successfully
- **THEN** the two `LocateResult.ax_fingerprint` values SHALL differ

### Requirement: `LocateResult.coords` carries L4 click target

The system SHALL extend `agent.locate.LocateResult` with an optional `coords: tuple[int, int] | None = None` field. For results produced by L1, L2, and L3, `coords` SHALL be `None`. For results produced by L4, `coords` SHALL be the `(cx, cy)` viewport pixel pair at the bbox center, and `selector` SHALL be the empty string `""`. Consumers of `LocateResult` SHALL discriminate between selector-based and coordinate-based targets by inspecting `result.coords is not None` (equivalently `result.tier == "L4_vision"`).

#### Scenario: L1/L2/L3 results have coords=None

- **WHEN** a caller obtains a `LocateResult` from `locate_l1`, `locate_l2`, or `locate_l3`
- **THEN** `result.coords` SHALL be `None`
- **AND** `result.selector` SHALL be a non-empty Playwright-locatable selector string

#### Scenario: L4 result has coords populated and empty selector

- **WHEN** a caller obtains a `LocateResult` from `locate_l4`
- **THEN** `result.coords` SHALL be a 2-tuple of integers
- **AND** `result.selector` SHALL equal `""`
- **AND** `result.tier` SHALL equal `"L4_vision"`

### Requirement: Vision LLM honors `LLM_BASE_URL`

When `locate_l4` is invoked without an `llm_chat` argument, it SHALL resolve the default `agent.llm.chat` callable lazily. The resolved callable SHALL post to the OpenAI-compatible chat-completions endpoint at the URL determined by `agent.llm`'s base-URL precedence: an explicit `base_url` argument, then the `LLM_BASE_URL` environment variable, then the module default `http://localhost:8090`. No alternative endpoint, no provider-specific URL, and no hardcoded host SHALL be used by the L4 path.

#### Scenario: Default L4 client posts to LLM_BASE_URL when set

- **GIVEN** the `LLM_BASE_URL` environment variable is set to `"http://vision.example.test"`
- **AND** the HTTP transport of `agent.llm` is mocked to capture outbound requests
- **WHEN** `locate_l4` is invoked with `llm_chat=None` (resolving the default)
- **THEN** the captured outbound request URL SHALL begin with `"http://vision.example.test/v1/chat/completions"`

#### Scenario: Default L4 client falls back to module default when LLM_BASE_URL unset

- **GIVEN** the `LLM_BASE_URL` environment variable is unset
- **AND** the HTTP transport of `agent.llm` is mocked to capture outbound requests
- **WHEN** `locate_l4` is invoked with `llm_chat=None`
- **THEN** the captured outbound request URL SHALL begin with `"http://localhost:8090/v1/chat/completions"`

## MODIFIED Requirements

### Requirement: Locator pipeline entry point

The system SHALL expose `agent.locate.locate(page, intent, *, llm_chat=None)` as the single entry point for resolving a natural-language intent to a unique element on the currently loaded Playwright page. `locate` SHALL parse the intent into `(role, name)` and call `locate_l1`. The cascade behaviour SHALL be:

1. If `locate_l1` returns successfully, `locate` SHALL return that result.
2. If `locate_l1` raises `LocatorMiss(reason="zero_matches")`, `locate` SHALL invoke `locate_l2(page, role=role, name=name)`. If `locate_l2` returns successfully, `locate` SHALL return that result. If `locate_l2` raises `LocatorMiss` (any reason), `locate` SHALL fall through to `locate_l4(page, role=role, name=name, intent=intent, llm_chat=llm_chat)` and return its result (or propagate its `LocatorMiss`).
3. If `locate_l1` raises `LocatorMiss(reason="ambiguous")`, `locate` SHALL invoke `locate_l3(page, role=role, name=name, llm_chat=llm_chat)`. If `locate_l3` returns successfully, `locate` SHALL return that result. If `locate_l3` raises `LocatorMiss` (any reason), `locate` SHALL fall through to `locate_l4(page, role=role, name=name, intent=intent, llm_chat=llm_chat)` and return its result (or propagate its `LocatorMiss`).

The `llm_chat` parameter SHALL be forwarded to `locate_l3` and `locate_l4`; passing `None` (the default) means the called tier will resolve the default `agent.llm.chat`. On success `locate` SHALL return a `LocateResult`. On failure it SHALL raise either `LocatorMiss` (UI-state failure — element absent or unresolvable after all wired-in tiers, including L4) or `IntentParseError` (the intent itself could not be parsed). `IntentParseError` SHALL NOT cascade to L4.

#### Scenario: Resolves a parseable intent via L1

- **GIVEN** a page exposing exactly one accessible element matching role `button` and accessible name `Submit`
- **WHEN** a caller invokes `locate(page, "Submit button")`
- **THEN** the call SHALL return a `LocateResult`
- **AND** `result.tier` SHALL equal `"L1_ax"`
- **AND** `result.role` SHALL equal `"button"`
- **AND** `result.name` SHALL equal `"Submit"`

#### Scenario: Falls through to L2 on L1 zero-match

- **GIVEN** a page where no element matches role `textbox` with accessible name `Email address` (so L1 returns zero matches)
- **AND** the page contains exactly one `<input placeholder="Email address">` resolvable by L2's placeholder strategy
- **WHEN** a caller invokes `locate(page, "Email address textbox")`
- **THEN** the call SHALL return a `LocateResult`
- **AND** `result.tier` SHALL equal `"L2_dom"`

#### Scenario: Falls through to L3 on L1 ambiguous

- **GIVEN** a page where two or more accessible buttons share the name `Save` (L1 returns `LocatorMiss(reason="ambiguous", match_count=N)`)
- **AND** a stub `llm_chat` that returns `{"index": 0}`
- **WHEN** a caller invokes `locate(page, "Save button", llm_chat=stub)`
- **THEN** the call SHALL return a `LocateResult`
- **AND** `result.tier` SHALL equal `"L3_rerank"`
- **AND** `result.role` SHALL equal `"button"`
- **AND** `result.name` SHALL equal `"Save"`

#### Scenario: Falls through to L4 when both L1 and L2 miss

- **GIVEN** a page that exposes no element resolvable by L1 or any L2 strategy for a given intent
- **AND** a target painted at known viewport coordinates with no accessible metadata
- **AND** a stub `llm_chat` that, when invoked with multimodal vision messages, returns `{"bbox": [x, y, w, h]}` covering the target
- **WHEN** a caller invokes `locate(page, "Submit button", llm_chat=stub)`
- **THEN** the call SHALL return a `LocateResult`
- **AND** `result.tier` SHALL equal `"L4_vision"`
- **AND** `result.coords` SHALL be a 2-tuple of integers inside the target's painted area

#### Scenario: Falls through to L4 when L3 cannot disambiguate

- **GIVEN** a page where L1 returns ambiguous on a given intent
- **AND** a stub `llm_chat` that, when invoked with the L3 rerank prompt, returns malformed JSON, but when invoked with the L4 vision prompt returns a valid bbox
- **WHEN** a caller invokes `locate(page, "Save button", llm_chat=stub)`
- **THEN** the call SHALL return a `LocateResult`
- **AND** `result.tier` SHALL equal `"L4_vision"`

#### Scenario: Surfaces unparseable intent without invoking L4

- **WHEN** a caller invokes `locate(page, "do the thing")` with no recognised trailing role keyword
- **AND** a stub `llm_chat` that fails the test if invoked
- **THEN** the call SHALL raise `IntentParseError`
- **AND** the exception message SHALL include the offending intent string
- **AND** the stub SHALL NOT have been invoked

#### Scenario: Surfaces vision_miss when all four tiers fail

- **GIVEN** a page that exposes no element resolvable by L1 or any L2 strategy for a given intent
- **AND** a stub `llm_chat` that returns malformed JSON for the L4 vision prompt
- **WHEN** a caller invokes `locate(page, intent, llm_chat=stub)`
- **THEN** the call SHALL raise `LocatorMiss`
- **AND** `LocatorMiss.reason` SHALL equal `"vision_miss"`

#### Scenario: L1 success short-circuits — L4 vision LLM is never invoked

- **GIVEN** a page exposing exactly one accessible element matching the intent (so L1 succeeds)
- **AND** a stub `llm_chat` that fails the test if invoked (e.g. raises `AssertionError`)
- **WHEN** a caller invokes `locate(page, "Submit button", llm_chat=stub)`
- **THEN** the call SHALL return a `LocateResult` with `tier == "L1_ax"`
- **AND** the stub SHALL NOT have been invoked

### Requirement: `LocateResult` shared shape

The system SHALL define `agent.locate.LocateResult` as a dataclass with the fields `tier: str`, `role: str`, `name: str | None`, `selector: str`, `ax_fingerprint: str`, `confidence: float`, and `coords: tuple[int, int] | None = None` (defaulting to `None`). This shape SHALL be the contract between the locator pipeline and its consumers (the agent loop, the supervisor, the locator cache, the trace writer); all tiers SHALL populate the same fields. L1, L2, and L3 SHALL leave `coords` at `None`. L4 SHALL populate `coords` and SHALL set `selector` to the empty string `""`.

#### Scenario: Result is constructible and round-trippable through Playwright

- **GIVEN** a `LocateResult` returned by `locate_l1` for a unique button
- **WHEN** a caller invokes `page.locator(result.selector)`
- **THEN** the resulting Playwright `Locator` SHALL refer to the same DOM element that produced the result

#### Scenario: AX fingerprint is deterministic for the same role+name

- **WHEN** two `LocateResult`s are produced by L1 for the same `(role, name)` pair against accessibility nodes that share the same role and accessible name
- **THEN** their `ax_fingerprint` values SHALL be equal

#### Scenario: coords is None for selector-based tiers

- **WHEN** a `LocateResult` is produced by `locate_l1`, `locate_l2`, or `locate_l3`
- **THEN** `result.coords` SHALL be `None`

#### Scenario: coords carries the click center for L4 tier

- **WHEN** a `LocateResult` is produced by `locate_l4`
- **THEN** `result.coords` SHALL be a 2-tuple `(int, int)`
- **AND** `result.selector` SHALL equal `""`

### Requirement: Module-local locator exception types

The system SHALL define `LocateError`, `LocatorMiss`, and `IntentParseError` as exception classes in `agent.locate`. `LocatorMiss` and `IntentParseError` SHALL each be subclasses of `LocateError`. `LocatorMiss` SHALL carry a `reason` attribute restricted to `"zero_matches"`, `"ambiguous"`, or `"vision_miss"`, and SHALL carry an integer `match_count` attribute (zero for `"zero_matches"` and `"vision_miss"`, the actual count for `"ambiguous"`). These types SHALL be importable directly from `agent.locate` so callers can catch them by type rather than parsing message strings.

#### Scenario: Exception types are importable and form a hierarchy

- **WHEN** a caller executes `from agent.locate import LocateError, LocatorMiss, IntentParseError`
- **THEN** the import SHALL succeed
- **AND** `LocatorMiss` and `IntentParseError` SHALL each be subclasses of `LocateError`

#### Scenario: LocatorMiss reason is constrained

- **WHEN** code constructs `LocatorMiss(reason="zero_matches", match_count=0)`
- **THEN** the construction SHALL succeed
- **AND** `miss.reason` SHALL equal `"zero_matches"`
- **AND** `miss.match_count` SHALL equal `0`

#### Scenario: LocatorMiss accepts vision_miss reason

- **WHEN** code constructs `LocatorMiss(reason="vision_miss", match_count=0)`
- **THEN** the construction SHALL succeed
- **AND** `miss.reason` SHALL equal `"vision_miss"`
- **AND** `miss.match_count` SHALL equal `0`

#### Scenario: LocatorMiss rejects unknown reasons

- **WHEN** code constructs `LocatorMiss(reason="something_else", match_count=0)`
- **THEN** the construction SHALL raise `ValueError`
