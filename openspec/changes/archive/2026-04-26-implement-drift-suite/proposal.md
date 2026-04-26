## Why

The agent's self-maintenance claim is currently untestable in CI: there are no fixture pages that exercise selector drift, so it is impossible to verify the L1→L2/L3 fallback ladder handles renamed/moved selectors. Ticket #16 closes this gap by providing a pair of static HTML fixtures (v1 and v2) with identical semantics but renamed selectors, an eval case that runs the same NL task against both variants, and assertions that confirm the locator ladder resolves each variant at the expected tier without any code change.

## What Changes

- Two static HTML fixture files under `task2/tests/fixtures/drift/submit-form/v1/index.html` and `.../v2/index.html`: identical task semantics (a submit button + a text input), but v1 uses standard semantic markup (AX-resolvable at L1) while v2 renames the button's accessible name so L1 misses and falls through to L2.
- One eval YAML case file `task2/eval/cases/drift-submit-form.yaml` with `category: drift` and a `variants` list (`[v1, v2]`) so the eval runner drives the same NL task against both fixture pages and records a separate result row per variant.
- Eval runner extended to understand the `variants` field: when a case has `variants`, the runner expands it into per-variant runs whose IDs are `<case-id>-v1`, `<case-id>-v2`, etc., each pointing to `tests/fixtures/drift/<case-id>/<variant>/index.html` served by the test fixture server.
- New test module `task2/tests/test_drift.py` with two kinds of assertions:
  - **Tier assertions**: v1 resolves at `L1_ax`; v2 resolves at `L2_dom`. Confirmed by inspecting `LocateResult.tier` from a real (Playwright-backed) `locate()` call against each fixture.
  - **Eval-suite assertion**: both variants produce `status == "succeeded"` in the results JSON (same task, both pass, no code change).
- The `drift-suite` pass gate (100% required, per plan) is satisfied when this test module passes.

## Capabilities

### New Capabilities

- `drift-suite`: Static fixture pair (v1 with standard AX markup, v2 with renamed/moved selectors) plus an eval case with a `variants` field. Proves the locator ladder resolves both variants of the same task without code changes. Includes tier-assertion tests confirming which L-tier resolves each variant.

### Modified Capabilities

- `eval-runner`: The `variants` field in a YAML case is a new optional key; the runner must expand a variantized case into N sub-runs and emit one `CaseResult` per variant in the results JSON.

## Impact

- **New files**: `task2/tests/fixtures/drift/submit-form/v1/index.html`, `task2/tests/fixtures/drift/submit-form/v2/index.html`, `task2/eval/cases/drift-submit-form.yaml`, `task2/tests/test_drift.py`.
- **Modified files**: `task2/scripts/eval.py` (variant expansion logic); `task2/tests/test_eval.py` (new test covering the variant-expansion path).
- **Dependencies**: no new Python packages; uses existing `pyyaml`, `playwright`, `pytest`, the existing `fixture_server` conftest fixture.
- **Env vars**: none new; `FIXTURE_BASE_URL` (or the conftest's existing local server) used to serve drift fixture files.
- **Existing modules**: `agent/locate.py` and the locator pipeline are exercised but NOT modified — this ticket is purely additive.
