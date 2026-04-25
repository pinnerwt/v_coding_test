## 1. Test fixtures (red prep)

- [ ] 1.1 Create `task2/tests/fixtures/locate_l2_placeholder.html` containing exactly one `<input type="text" placeholder="Email address">` with no `<label>`, no `aria-label`, no `aria-labelledby`, and no enclosing `<label>`. Add a sibling text node so the page is non-empty but otherwise unrelated to the input.
- [ ] 1.2 Create `task2/tests/fixtures/locate_l2_nonsemantic.html` containing exactly one `<div class="btn" onclick="void 0">Submit</div>` and a `<p>` of unrelated body text. No `<button>`, no `role`, no `aria-*`.
- [ ] 1.3 Create `task2/tests/fixtures/locate_l2_ambiguous.html` containing two `<div class="btn" onclick="void 0">Save</div>` elements in two distinct `<section>`s with different headings. No real `<button>`s with name `Save` (so L1 returns zero; L2 text-contains returns 2).
- [ ] 1.4 Create `task2/tests/fixtures/locate_l2_cascade.html` containing exactly one `<input placeholder="Phone number">` and no element resolvable as a `textbox` by L1 (no labels) — used by the orchestrator-cascade test.
- [ ] 1.5 Confirm `task2/tests/conftest.py` already exposes `fixture_server` and `playwright_chromium`; no conftest change needed.

## 2. Failing tests (red)

- [ ] 2.1 Add `task2/tests/agent/test_locate_l2.py`. Import `locate, locate_l1, locate_l2, LocateResult, LocatorMiss` from `agent.locate` so the import alone fails until `locate_l2` exists.
- [ ] 2.2 Write `test_locate_l2_placeholder_unique` against `locate_l2_placeholder.html` — assert returned `LocateResult.tier == "L2_dom"`, `role == "textbox"`, `name == "Email address"`, `confidence == 0.7`, `ax_fingerprint` non-empty, and `page.locator(result.selector)` resolves to exactly one element whose tag is `INPUT` and whose `placeholder` attribute equals `Email address`.
- [ ] 2.3 Write `test_locate_l2_nonsemantic_clickable_unique` against `locate_l2_nonsemantic.html` — assert `LocateResult.tier == "L2_dom"`, `role == "button"`, `name == "Submit"`, `page.locator(result.selector)` resolves to a single `<div>` with class `btn`.
- [ ] 2.4 Write `test_locate_l2_ambiguous` against `locate_l2_ambiguous.html` — assert `LocatorMiss` with `reason == "ambiguous"` and `match_count == 2`.
- [ ] 2.5 Write `test_locate_l2_zero_matches` against any L2 fixture using a name no element matches (e.g. `locate_l2_placeholder.html` with `name="Refund button"` or a fresh fixture) — assert `LocatorMiss` with `reason == "zero_matches"` and `match_count == 0`.
- [ ] 2.6 Write `test_locate_l2_unsupported_role_short_circuits` — call `locate_l2(page, role="heading", name="Welcome")` against `locate_l2_placeholder.html`; assert `LocatorMiss` with `reason == "zero_matches"` and `match_count == 0`. Also assert that no `page.get_by_*` query is invoked (verify by spying via `monkeypatch` on the module's strategy entry points, or by asserting timing is sub-millisecond as a weaker proxy).
- [ ] 2.7 Write `test_locate_l2_empty_name_short_circuits` — call `locate_l2(page, role="button", name=None)`; assert `LocatorMiss(reason="zero_matches", match_count=0)`.
- [ ] 2.8 Write `test_locate_orchestrator_cascades_l1_zero_to_l2` against `locate_l2_cascade.html` — call `locate(page, "Phone number textbox")`; assert returned `LocateResult.tier == "L2_dom"` (proves L1 missed and L2 caught it).
- [ ] 2.9 Write `test_locate_orchestrator_does_not_cascade_on_l1_ambiguous` against the existing `locate_l1.html` fixture — call `locate(page, "Save button")`; assert `LocatorMiss` with `reason == "ambiguous"` and `match_count == 2` (the L1 ambiguity surfaces unchanged).
- [ ] 2.10 Write `test_locate_orchestrator_surfaces_l2_zero_match` — point at a fixture where neither L1 nor L2 resolves the intent (e.g. a page containing only the placeholder input but querying `"Refund button"`); assert `LocatorMiss` with `reason == "zero_matches"`.
- [ ] 2.11 Write `test_l2_fingerprint_independent_of_dom_path` — load two distinct fixtures each containing a `<div onclick>Submit</div>` with different `class` attributes and different parent structures (use the existing nonsemantic fixture and a second variant `locate_l2_nonsemantic_alt.html`); assert the two `LocateResult.ax_fingerprint` values are equal.
- [ ] 2.12 From `task2/`, run `uv run pytest tests/agent/test_locate_l2.py -x` and confirm every test fails for the expected reason (missing `locate_l2` symbol, or orchestrator not yet cascading), not for setup or fixture errors. Existing `tests/agent/test_locate.py` SHALL still be all-green.

## 3. Implementation (green)

- [ ] 3.1 In `task2/agent/locate.py`, add `_L2_BUTTON_TAXONOMY_CSS` and `_L2_LINK_TAXONOMY_CSS` module constants holding the comma-separated CSS selectors from the design doc (button: `button, input[type=button], input[type=submit], input[type=reset], [role=button], [onclick], [class*="btn"], [class*="button"]`; link: `a[href], [role=link]`).
- [ ] 3.2 Add an internal `_l2_strategies(role)` helper that returns an ordered list of `(strategy_id, builder_fn)` for the given role: `[("placeholder", ...)]` for `textbox`, `[("text_contains", ...)]` for `button` and `link`, `[]` for any other role.
- [ ] 3.3 Implement `locate_l2(page, *, role, name) -> LocateResult`: short-circuit with `LocatorMiss(reason="zero_matches", match_count=0)` if `name` is empty/`None` or if `_l2_strategies(role)` is empty; otherwise iterate strategies in order, count matches, return on first count==1, track first non-empty (>1) count for the ambiguous fallback; if no strategy returned 1, raise `LocatorMiss(reason="ambiguous", match_count=first_non_empty_count)` if any non-empty strategy ran, else `LocatorMiss(reason="zero_matches", match_count=0)`.
- [ ] 3.4 For the **placeholder** strategy: build via `page.get_by_placeholder(name, exact=False)`. Compute the synthesised selector as `f'[placeholder*="{escaped}" i]'` where `escaped` re-uses the existing L1 quote-escape (`\\` → `\\\\`, `"` → `\\"`).
- [ ] 3.5 For the **text-contains** strategy: build via `page.locator(taxonomy_css).filter(has_text=name)`. Compute the synthesised selector as `f"{taxonomy_css} >> text={name!r}"` — Playwright accepts `>> text=...` as a stable string-form locator. Verify in a unit assertion (in test 2.2/2.3) that `page.locator(result.selector).count() == 1`.
- [ ] 3.6 Compute `ax_fingerprint` as `sha256(f"{role}:{name}:{strategy_id}".encode()).hexdigest()` for the winning strategy. Do NOT include any DOM-derived data in the fingerprint.
- [ ] 3.7 Build `LocateResult(tier="L2_dom", role=role, name=name, selector=selector, ax_fingerprint=fingerprint, confidence=0.7)` for the winning strategy.
- [ ] 3.8 Modify `locate(page, intent)` to wrap the existing `locate_l1` call in a `try/except LocatorMiss`: on `miss.reason == "zero_matches"` call `locate_l2(page, role=role, name=name)` and return its result (allowing its `LocatorMiss` to propagate). On any other `reason`, re-raise.
- [ ] 3.9 From `task2/`, run `uv run pytest tests/agent/test_locate_l2.py` and confirm all new tests pass.
- [ ] 3.10 From `task2/`, run `uv run pytest` (full suite) and confirm tickets #1, #2, #3 tests still pass — in particular `test_locate_orchestrator_runs_l1` (the L1 happy-path orchestrator test) is not affected by the new cascade.

## 4. Refactor + housekeeping

- [ ] 4.1 Re-read `task2/agent/locate.py` for one-shot helpers, dead branches, or premature abstractions; inline anything called once. Specifically check that `_l2_strategies` is justified (more than one caller or clarity benefit) — if only `locate_l2` uses it and the tier list is short, consider inlining.
- [ ] 4.2 Confirm L1 `locate_l1` is unmodified (cascade lives in `locate`, not in `locate_l1`).
- [ ] 4.3 Confirm `LocateResult`'s field order and frozen-ness are unchanged from ticket #3.
- [ ] 4.4 From `task2/`, run `uv run ruff format .` and stage any changes; run `uv run ruff check .` and resolve findings.
- [ ] 4.5 Confirm no new dependencies were added to `task2/pyproject.toml`.

## 5. Validation

- [ ] 5.1 Run `openspec validate implement-locate-l2 --strict` from the repo root and resolve any findings.
- [ ] 5.2 From `task2/`, final pre-commit gate: `uv run ruff format . && uv run ruff check . && uv run pytest` — all clean.
- [ ] 5.3 Stage commits in conventional-commit style (`test(task2): ...`, `feat(task2): ...`, `refactor(task2): ...`) preserving real history; never `--no-verify`.
