## 1. Test fixtures (red prep)

- [x] 1.1 Create `task2/tests/fixtures/locate_l1.html` containing: `<button>Submit</button>` (real); `<div role="button" aria-label="Cancel">Cancel</div>` (AX spoofer with different name); `<div class="btn">Submit</div>` (non-semantic look-alike — same text, no role); a section containing two `<button>Save</button>` elements in distinct labelled regions for the ambiguous-match scenario; one `<h1>Welcome</h1>` for the bare-role scenario.
- [x] 1.2 Confirm `task2/tests/conftest.py` already exposes `fixture_server` and `playwright_chromium` (added in ticket #2). No conftest change needed.

## 2. Failing tests (red)

- [x] 2.1 Add `task2/tests/agent/test_locate.py`. Import `locate, locate_l1, parse_intent, LocateResult, LocateError, LocatorMiss, IntentParseError` from `agent.locate` so the import alone fails until the module exists.
- [x] 2.2 Write `test_exception_hierarchy` asserting `LocatorMiss` and `IntentParseError` are subclasses of `LocateError`.
- [x] 2.3 Write `test_locator_miss_constrains_reason` asserting `LocatorMiss(reason="zero_matches", match_count=0)` constructs and that `LocatorMiss(reason="bogus", match_count=0)` raises `ValueError`.
- [x] 2.4 Write `parse_intent` cases (parametrised): `"Submit button" → ("button", "Submit")`, `"the Submit button" → ("button", "Submit")`, `"a Save link" → ("link", "Save")`, `"Email address textbox" → ("textbox", "Email address")`, `"button" → ("button", None)`.
- [x] 2.5 Write `parse_intent` failure cases: unknown role token (`"Submit widget"` → `IntentParseError`, message includes `"widget"`), empty/whitespace intent (`"   "` → `IntentParseError`).
- [x] 2.6 Write `test_locate_l1_unique_match` against `locate_l1.html` — assert returned `LocateResult.tier == "L1_ax"`, `role == "button"`, `name == "Submit"`, `confidence == 1.0`, `ax_fingerprint` non-empty, and `page.locator(result.selector)` resolves to the real `<button>` (verify by `text_content() == "Submit"` and tag-name check via `evaluate("el => el.tagName")`).
- [x] 2.7 Write `test_locate_l1_zero_matches` — query a role+name with no AX hit (e.g. `name="Nonexistent"`); assert `LocatorMiss` with `reason == "zero_matches"` and `match_count == 0`.
- [x] 2.8 Write `test_locate_l1_ambiguous` — query the two `<button>Save</button>` elements; assert `LocatorMiss` with `reason == "ambiguous"` and `match_count == 2`.
- [x] 2.9 Write `test_locate_l1_non_semantic_invisible` — confirm the bare-`<div class="btn">Submit</div>` does *not* satisfy a `role="button", name="Submit"` query when the real button is removed (use a separate fixture or remove via `page.evaluate` if simpler — preferred: a second tiny fixture `locate_l1_div_only.html` containing only the `<div>`).
- [x] 2.10 Write `test_locate_l1_bare_role` — `locate_l1(page, role="heading", name=None)` against the `<h1>Welcome</h1>` returns a unique L1 result.
- [x] 2.11 Write `test_ax_fingerprint_deterministic` — two L1 lookups for the same `(role, name)` against the same page produce equal `ax_fingerprint`.
- [x] 2.12 Write `test_locate_orchestrator_runs_l1` — `locate(page, "Submit button")` returns the same `LocateResult` shape as `locate_l1` directly.
- [x] 2.13 Write `test_locate_orchestrator_propagates_intent_error` — `locate(page, "do the thing")` raises `IntentParseError`.
- [x] 2.14 From `task2/`, run `uv run pytest tests/agent/test_locate.py -x` and confirm every test fails for the expected reason (missing module / missing symbols), not for setup or fixture errors.

## 3. Implementation (green)

- [x] 3.1 Create `task2/agent/locate.py` with the public surface in this order: constants (`_SUPPORTED_ROLES`, `_ARTICLES`), exception hierarchy (`LocateError`, `LocatorMiss`, `IntentParseError`), `LocateResult` dataclass (frozen), `parse_intent`, `locate_l1`, `locate`.
- [x] 3.2 Implement `LocatorMiss` to validate `reason` against `{"zero_matches", "ambiguous"}` in `__init__` (raise `ValueError` on unknown), store `reason` and `match_count` as attributes, and call `super().__init__` with a human-readable message.
- [x] 3.3 Implement `parse_intent`: strip; split on whitespace; if empty raise `IntentParseError`; drop a single leading article if it matches `_ARTICLES` (case-insensitive); take the trailing token lowercased as `role`; reject if not in `_SUPPORTED_ROLES` (`IntentParseError` mentioning the offending token); join remaining tokens with single spaces as `name` (or `None` if empty).
- [x] 3.4 Implement `locate_l1`: build the Playwright `Locator` via `page.get_by_role(role, name=name, exact=False)` when `name` is truthy, else `page.get_by_role(role)`; call `.count()`; on 0 raise `LocatorMiss(reason="zero_matches", match_count=0)`; on >1 raise `LocatorMiss(reason="ambiguous", match_count=count)`; on 1 build a stable role-locator selector string (e.g. `f'role={role}[name="{name}" i]'` for named queries, `f"role={role}"` for bare ones), compute `ax_fingerprint = sha256(f"{role}:{name or ''}".encode()).hexdigest()`, return `LocateResult(tier="L1_ax", role=role, name=name, selector=selector, ax_fingerprint=fingerprint, confidence=1.0)`.
- [x] 3.5 Implement `locate(page, intent)` as `parse_intent` → `locate_l1`. No tier-routing logic (later tickets add it).
- [x] 3.6 From `task2/`, run `uv run pytest tests/agent/test_locate.py` and confirm all tests pass.
- [x] 3.7 From `task2/`, run `uv run pytest` (full suite) and confirm ticket #1 + #2 tests still pass.

## 4. Refactor + housekeeping

- [x] 4.1 Re-read `task2/agent/locate.py` for one-shot helpers, dead branches, or premature abstractions; inline anything called once. Specifically check that the selector-string builder is not extracted unless it has more than one caller.
- [x] 4.2 Confirm `LocateResult` is frozen and its field order matches the spec's stated contract (`tier, role, name, selector, ax_fingerprint, confidence`).
- [x] 4.3 From `task2/`, run `uv run ruff format .` and stage any changes; run `uv run ruff check .` and resolve findings (no `--no-fix` blanket overrides).
- [x] 4.4 Confirm no new dependencies were added to `task2/pyproject.toml`; if any sneaked in, remove them.

## 5. Validation

- [x] 5.1 Run `openspec validate implement-locate-l1 --strict` and resolve any findings.
- [x] 5.2 From `task2/`, final pre-commit gate: `uv run ruff format . && uv run ruff check . && uv run pytest` — all clean.
- [x] 5.3 Stage commits in conventional-commit style (`test(task2): ...`, `feat(task2): ...`, `refactor(task2): ...`) preserving real history; never `--no-verify`.
