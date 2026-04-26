## 1. Drift fixture HTML files

- [ ] 1.1 Create directory `task2/tests/fixtures/drift/submit-form/v1/`.
- [ ] 1.2 Create `task2/tests/fixtures/drift/submit-form/v1/index.html`: minimal HTML with `<button>Submit</button>` and `<input type="text" placeholder="Name">`. No scripts, no inline styles needed.
- [ ] 1.3 Create directory `task2/tests/fixtures/drift/submit-form/v2/`.
- [ ] 1.4 Create `task2/tests/fixtures/drift/submit-form/v2/index.html`: same visible structure as v1 but replace `<button>Submit</button>` with `<div class="btn" onclick="void(0)">Submit</div>` (no `role`, no `aria-*`). Keep `<input type="text" placeholder="Name">` identical.
- [ ] 1.5 Verify v1: from `task2/`, run `uv run python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(headless=True); pg = b.new_page(); pg.goto('file://$(pwd)/tests/fixtures/drift/submit-form/v1/index.html'); print(pg.get_by_role('button', name='Submit').count()); b.close(); p.stop()"` and confirm output is `1`.
- [ ] 1.6 Verify v2: same script with v2 path — confirm `get_by_role('button', name='Submit').count()` returns `0` and `page.locator('[class*="btn"]').filter(has_text="Submit").count()` returns `1`.

## 2. Drift eval YAML case

- [ ] 2.1 Create `task2/eval/cases/drift-submit-form.yaml` with fields: `id: drift-submit-form`, `domain: fixture`, `category: drift`, `task: "Click the submit button and return submitted as status"`, `expect: { schema: { status: str }, validators: [status.nonempty] }`, `budget: { steps: 5, usd: 0.05, seconds: 30 }`, `fixture: true`, `variants: [v1, v2]`.
- [ ] 2.2 From `task2/`, run `uv run python -c "from scripts.eval import load_cases; c = load_cases('eval/cases/drift-submit-form.yaml'); print(c[0]['variants'])"` and confirm output is `['v1', 'v2']`.

## 3. Red — Failing tests (tier assertions and eval variant expansion)

- [ ] 3.1 Create `task2/tests/test_drift.py`. Add import `from agent.locate import locate` and `from agent.locate import LocateResult` — confirm the file is importable with `uv run pytest tests/test_drift.py --collect-only`.
- [ ] 3.2 Add `test_v1_resolves_at_l1`: use `playwright_chromium` and `fixture_server` fixtures. Navigate to `{fixture_server}/drift/submit-form/v1/index.html`. Call `locate(page, "Submit button")`. Assert `result.tier == "L1_ax"` and `result.confidence == 1.0`. Run `uv run pytest tests/test_drift.py::test_v1_resolves_at_l1 -x` — confirm it fails (fixture file does not yet exist or locate raises). This is the red state.
- [ ] 3.3 Add `test_v2_resolves_at_l2`: same setup, navigate to v2 URL. Call `locate(page, "Submit button")`. Assert `result.tier == "L2_dom"` and `result.confidence == 0.7`. Confirm red state.
- [ ] 3.4 Add `test_same_intent_both_variants_succeed`: navigate to v1, call `locate(page, "Submit button")`, store `r1`. Navigate to v2, call `locate(page, "Submit button")`, store `r2`. Assert neither raises and `r1.tier != r2.tier` (v1 resolves higher than v2). Confirm red state.
- [ ] 3.5 In `task2/tests/test_eval.py`, add `test_drift_case_yaml_loads`: call `load_cases("eval/cases/drift-submit-form.yaml")`; assert `cases[0]["id"] == "drift-submit-form"`, `cases[0]["variants"] == ["v1", "v2"]`, `cases[0]["fixture"] is True`. Run the test — confirm red state (YAML file may already exist after task 2.1, so this may pass early; confirm it passes before proceeding).
- [ ] 3.6 In `task2/tests/test_eval.py`, add `test_variant_expansion_produces_two_results`: define an inline drift case dict with `variants: ["v1", "v2"]` and `fixture: True`. Patch `scripts.eval.loop` with `side_effect=[_CANNED_RESULT, _CANNED_RESULT]` (two successful results). Call `run_suite(cases=[drift_case], results_dir=tmp_path)`. Assert `len(data["cases"]) == 2`. Assert `data["cases"][0]["id"] == "drift-submit-form-v1"` and `data["cases"][1]["id"] == "drift-submit-form-v2"`. Run — confirm red state (variant expansion not implemented yet).
- [ ] 3.7 In `task2/tests/test_eval.py`, add `test_variant_expansion_mixed_suite`: define an inline suite with one non-variantized fixture case and one variantized drift case (2 variants). Patch `scripts.eval.loop` with 3 `side_effect` values. Assert results JSON has 3 entries total. Confirm red state.

## 4. Green — Implement variant expansion in `scripts/eval.py`

- [ ] 4.1 In `scripts/eval.py`, add a private helper `_expand_variants(cases: list[dict]) -> list[dict]` that iterates each case: if the case has a `variants` key with a non-empty list, it yields one shallow-copy dict per variant with `id` set to `<orig-id>-<variant>` and a `_variant` key set to the variant string; if `variants` is absent or empty it yields the case unchanged. No other fields are modified.
- [ ] 4.2 Call `_expand_variants` at the top of `run_suite` before the loop: `cases = _expand_variants(cases)`. No other change to `run_suite`.
- [ ] 4.3 From `task2/`, run `uv run pytest tests/test_eval.py -x -k "variant"` and confirm all variant-expansion tests pass (green for variant tests).
- [ ] 4.4 From `task2/`, run `uv run pytest tests/test_eval.py` and confirm zero regressions in existing eval tests.

## 5. Green — Make tier-assertion tests pass

- [ ] 5.1 Confirm that `task2/tests/fixtures/drift/submit-form/v1/index.html` and `v2/index.html` exist (created in task group 1). If not, create them now.
- [ ] 5.2 From `task2/`, run `uv run pytest tests/test_drift.py -x` and confirm all three tier-assertion tests pass (green).
- [ ] 5.3 If `test_v2_resolves_at_l2` fails with `LocatorMiss` rather than returning `tier=="L2_dom"`, verify the v2 HTML has the `btn` class name on the `<div>` — the L2 button taxonomy includes `[class*="btn"]`. Fix the HTML if needed, rerun until green.

## 6. Green — Full test suite

- [ ] 6.1 From `task2/`, run `uv run pytest tests/test_drift.py tests/test_eval.py -v` and confirm all new tests pass.
- [ ] 6.2 From `task2/`, run `uv run pytest` (full suite) and confirm zero regressions.

## 7. Lint and format

- [ ] 7.1 From `task2/`, run `uv run ruff check --fix .` to auto-fix any lint issues introduced by the `_expand_variants` addition.
- [ ] 7.2 From `task2/`, run `uv run ruff format .` to auto-format changed files.
- [ ] 7.3 From `task2/`, run `uv run ruff check .` and confirm it exits clean.

## 8. Refactor under green

- [ ] 8.1 Verify `_expand_variants` in `scripts/eval.py` contains no comments or docstrings (per the no-docstrings rule for production code).
- [ ] 8.2 Verify `task2/agent/locate.py` is unchanged (`git diff task2/agent/locate.py` shows no modifications) — the drift suite must pass without any locator code changes.
- [ ] 8.3 From `task2/`, run `uv run ruff format . && uv run ruff check . && uv run pytest` in sequence; all three must exit clean.
