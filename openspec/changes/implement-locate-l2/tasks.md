## 1. Test fixtures (red prep)

- [x] 1.1 Create `task2/tests/fixtures/locate_l2_placeholder.html` containing exactly one `<input type="text" placeholder="Email address">` with no `<label>`, no `aria-label`, no `aria-labelledby`, and no enclosing `<label>`. Add a sibling text node so the page is non-empty but otherwise unrelated to the input.
- [x] 1.2 Create `task2/tests/fixtures/locate_l2_nonsemantic.html` containing exactly one `<div class="btn" onclick="void 0">Submit</div>` and a `<p>` of unrelated body text. No `<button>`, no `role`, no `aria-*`.
- [x] 1.3 Create `task2/tests/fixtures/locate_l2_ambiguous.html` containing two `<div class="btn" onclick="void 0">Save</div>` elements in two distinct `<section>`s with different headings. No real `<button>`s with name `Save` (so L1 returns zero; L2 text-contains returns 2).
- [x] 1.4 ~~Create `task2/tests/fixtures/locate_l2_cascade.html`~~ Dropped during green: Playwright's L1 `get_by_role(textbox, name=...)` already matches `<input>` by placeholder text, so a placeholder-only fixture is not a real L1 miss. The cascade test instead reuses `locate_l2_nonsemantic.html` (a `<div onclick>Submit</div>`), which is the genuine L1-miss / L2-hit case.
- [x] 1.5 Confirm `task2/tests/conftest.py` already exposes `fixture_server` and `playwright_chromium`; no conftest change needed.

## 2. Failing tests (red)

- [x] 2.1 Add `task2/tests/agent/test_locate_l2.py`. Import `locate, locate_l1, locate_l2, LocateResult, LocatorMiss` from `agent.locate` so the import alone fails until `locate_l2` exists.
- [x] 2.2 Write `test_locate_l2_placeholder_unique` against `locate_l2_placeholder.html` — assert returned `LocateResult.tier == "L2_dom"`, `role == "textbox"`, `name == "Email address"`, `confidence == 0.7`, `ax_fingerprint` non-empty, and `page.locator(result.selector)` resolves to exactly one element whose tag is `INPUT` and whose `placeholder` attribute equals `Email address`.
- [x] 2.3 Write `test_locate_l2_nonsemantic_clickable_unique` against `locate_l2_nonsemantic.html` — assert `LocateResult.tier == "L2_dom"`, `role == "button"`, `name == "Submit"`, `page.locator(result.selector)` resolves to a single `<div>` with class `btn`.
- [x] 2.4 Write `test_locate_l2_ambiguous` against `locate_l2_ambiguous.html` — assert `LocatorMiss` with `reason == "ambiguous"` and `match_count == 2`.
- [x] 2.5 Write `test_locate_l2_zero_matches` against any L2 fixture using a name no element matches (e.g. `locate_l2_placeholder.html` with `name="Refund button"` or a fresh fixture) — assert `LocatorMiss` with `reason == "zero_matches"` and `match_count == 0`.
- [x] 2.6 Write `test_locate_l2_unsupported_role_short_circuits` — call `locate_l2(page, role="heading", name="Welcome")` against `locate_l2_placeholder.html`; assert `LocatorMiss` with `reason == "zero_matches"` and `match_count == 0`. Also assert that no `page.get_by_*` query is invoked (verify by spying via `monkeypatch` on the module's strategy entry points, or by asserting timing is sub-millisecond as a weaker proxy).
- [x] 2.7 Write `test_locate_l2_empty_name_short_circuits` — call `locate_l2(page, role="button", name=None)`; assert `LocatorMiss(reason="zero_matches", match_count=0)`.
- [x] 2.8 Write `test_locate_orchestrator_cascades_l1_zero_to_l2` against `locate_l2_nonsemantic.html` — call `locate(page, "Submit button")`; assert returned `LocateResult.tier == "L2_dom"` (proves L1 missed and L2 caught it). Original plan was a placeholder-only fixture, but L1 already covers placeholder so a non-semantic clickable is the only real cascade case.
- [x] 2.9 Write `test_locate_orchestrator_does_not_cascade_on_l1_ambiguous` against the existing `locate_l1.html` fixture — call `locate(page, "Save button")`; assert `LocatorMiss` with `reason == "ambiguous"` and `match_count == 2` (the L1 ambiguity surfaces unchanged).
- [x] 2.10 Write `test_locate_orchestrator_surfaces_l2_zero_match` — point at a fixture where neither L1 nor L2 resolves the intent (e.g. a page containing only the placeholder input but querying `"Refund button"`); assert `LocatorMiss` with `reason == "zero_matches"`.
- [x] 2.11 Write `test_l2_fingerprint_independent_of_dom_path` — load two distinct fixtures each containing a `<div onclick>Submit</div>` with different `class` attributes and different parent structures (use the existing nonsemantic fixture and a second variant `locate_l2_nonsemantic_alt.html`); assert the two `LocateResult.ax_fingerprint` values are equal.
- [x] 2.12 From `task2/`, run `uv run pytest tests/agent/test_locate_l2.py -x` and confirm every test fails for the expected reason (missing `locate_l2` symbol, or orchestrator not yet cascading), not for setup or fixture errors. Existing `tests/agent/test_locate.py` SHALL still be all-green.

## 3. Implementation (green)

- [x] 3.1 In `task2/agent/locate.py`, add `_L2_BUTTON_TAXONOMY_CSS` and `_L2_LINK_TAXONOMY_CSS` module constants holding the comma-separated CSS selectors from the design doc (button: `button, input[type=button], input[type=submit], input[type=reset], [role=button], [onclick], [class*="btn"], [class*="button"]`; link: `a[href], [role=link]`).
- [x] 3.2 ~~Add an internal `_l2_strategies(role)` helper~~ Inlined — only one caller (`locate_l2`) and the role-to-strategy mapping is three branches; an extra helper added no clarity.
- [x] 3.3 Implement `locate_l2(page, *, role, name) -> LocateResult`: short-circuit with `LocatorMiss(reason="zero_matches", match_count=0)` if `name` is empty/`None` or if the role has no strategies; otherwise iterate strategies in order, count matches, return on first count==1, track first non-empty (>1) count for the ambiguous fallback; if no strategy returned 1, raise `LocatorMiss(reason="ambiguous", match_count=first_non_empty_count)` if any non-empty strategy ran, else `LocatorMiss(reason="zero_matches", match_count=0)`.
- [x] 3.4 For the **placeholder** strategy: build via `page.get_by_placeholder(name, exact=False)`. Compute the synthesised selector as `f'[placeholder*="{escaped}" i]'` where `escaped` re-uses the existing L1 quote-escape (`\\` → `\\\\`, `"` → `\\"`) via the new `_escape_quoted` helper.
- [x] 3.5 For the **text-contains** strategy: build via `page.locator(taxonomy_css).filter(has_text=name)`. Compute the synthesised selector as `f'{taxonomy_css} >> text="{escaped}"'` — Playwright accepts `>> text=...` as a stable string-form locator.
- [x] 3.6 Compute `ax_fingerprint` as `sha256(f"{role}:{name}:{strategy_id}".encode()).hexdigest()` for the winning strategy. Do NOT include any DOM-derived data in the fingerprint.
- [x] 3.7 Build `LocateResult(tier="L2_dom", role=role, name=name, selector=selector, ax_fingerprint=fingerprint, confidence=0.7)` for the winning strategy.
- [x] 3.8 Modify `locate(page, intent)` to wrap the existing `locate_l1` call in a `try/except LocatorMiss`: on `miss.reason == "zero_matches"` call `locate_l2(page, role=role, name=name)` and return its result (allowing its `LocatorMiss` to propagate). On any other `reason`, re-raise.
- [x] 3.9 From `task2/`, run `uv run pytest tests/agent/test_locate_l2.py` and confirm all new tests pass.
- [x] 3.10 From `task2/`, run `uv run pytest` (full suite) and confirm tickets #1, #2, #3 tests still pass — in particular `test_locate_orchestrator_runs_l1` (the L1 happy-path orchestrator test) is not affected by the new cascade.

## 4. Refactor + housekeeping

- [x] 4.1 Reread `task2/agent/locate.py`. Collapsed the per-role strategies list and `first_non_empty_count` bookkeeping into a single match — only one strategy fires per role today, so the loop was premature abstraction. Reused the existing `_escape_quoted` helper inside `locate_l1` to dedup the quote-escape inline.
- [x] 4.2 `locate_l1`'s control flow is unchanged; the cascade lives in `locate`.
- [x] 4.3 `LocateResult`'s field order and `@dataclass(frozen=True)` are unchanged.
- [x] 4.4 Ran `uv run ruff format .` (no further changes after the green commit) and `uv run ruff check .` (clean).
- [x] 4.5 No new dependencies added to `task2/pyproject.toml`.

## 5. Validation

- [ ] 5.1 Run `openspec validate implement-locate-l2 --strict` from the repo root and resolve any findings.
- [ ] 5.2 From `task2/`, final pre-commit gate: `uv run ruff format . && uv run ruff check . && uv run pytest` — all clean.
- [ ] 5.3 Stage commits in conventional-commit style (`test(task2): ...`, `feat(task2): ...`, `refactor(task2): ...`) preserving real history; never `--no-verify`.
