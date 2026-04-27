# drift-suite Specification

## Purpose
TBD - created by archiving change implement-drift-suite. Update Purpose after archive.
## Requirements

### Requirement: Drift fixture pair
The repository SHALL include two HTML fixture files under `task2/tests/fixtures/drift/submit-form/`:

- `v1/index.html` — a minimal HTML page containing a canonical `<button>Submit</button>` element resolvable by the L1 accessibility-tree tier. The page SHALL also contain one `<input type="text" placeholder="Name">` textbox.
- `v2/index.html` — the semantically equivalent page where the submit button is replaced by `<div class="btn" onclick="void(0)">Submit</div>`. The `<div>` element SHALL have no `role` attribute, no `aria-label`, and no `aria-labelledby`, so the L1 AX tier returns zero matches for `role=button`. The page SHALL otherwise have identical visible structure and task semantics to v1.

Both files SHALL be static HTML served without any server-side processing.

#### Scenario: v1 fixture has a semantic button element
- **WHEN** `task2/tests/fixtures/drift/submit-form/v1/index.html` is loaded
- **THEN** `page.get_by_role("button", name="Submit", exact=False).count()` SHALL equal `1`

#### Scenario: v2 fixture has no ARIA button element
- **WHEN** `task2/tests/fixtures/drift/submit-form/v2/index.html` is loaded
- **THEN** `page.get_by_role("button", name="Submit", exact=False).count()` SHALL equal `0`

#### Scenario: v2 fixture has a text-contains-matchable Submit element
- **WHEN** `task2/tests/fixtures/drift/submit-form/v2/index.html` is loaded
- **THEN** `page.locator('[class*="btn"]').filter(has_text="Submit").count()` SHALL equal `1`

### Requirement: Drift tier assertions
The system SHALL include tests in `task2/tests/test_drift.py` that call `agent.locate.locate(page, intent)` directly (no `loop()`, no LLM mock needed) against each variant's fixture HTML and assert the resolved `LocateResult.tier`.

These tests SHALL use real Playwright browser pages (via the `playwright_chromium` and `fixture_server` conftest fixtures) and SHALL NOT mock `locate()` or any part of the locator pipeline.

#### Scenario: v1 resolves at L1_ax
- **GIVEN** a Playwright page loaded with `tests/fixtures/drift/submit-form/v1/index.html`
- **WHEN** `locate(page, "Submit button")` is called
- **THEN** the returned `LocateResult.tier` SHALL equal `"L1_ax"`
- **AND** `LocateResult.confidence` SHALL equal `1.0`

#### Scenario: v2 resolves at L2_dom
- **GIVEN** a Playwright page loaded with `tests/fixtures/drift/submit-form/v2/index.html`
- **WHEN** `locate(page, "Submit button")` is called
- **THEN** the returned `LocateResult.tier` SHALL equal `"L2_dom"`
- **AND** `LocateResult.confidence` SHALL equal `0.7`

#### Scenario: Same intent string used for both variants
- **GIVEN** v1 and v2 fixture pages
- **WHEN** `locate(page, "Submit button")` is called on each without changing the intent string
- **THEN** both calls SHALL return a `LocateResult` (not raise any exception)
- **AND** both results SHALL refer to the same logical UI element (a submit affordance on the page)

### Requirement: Drift eval case YAML
The repository SHALL include `task2/eval/cases/drift-submit-form.yaml` defining a drift-suite eval case with the following required fields:

- `id: drift-submit-form`
- `domain: fixture`
- `category: drift`
- `task: "Click the submit button and return submitted as status"`
- `expect.schema: { status: str }`
- `expect.validators: [status.nonempty]`
- `budget: { steps: 5, usd: 0.05, seconds: 30 }`
- `fixture: true`
- `variants: [v1, v2]`

#### Scenario: Drift case YAML loads without error
- **WHEN** `task2/eval/cases/drift-submit-form.yaml` is loaded via `scripts.eval.load_cases`
- **THEN** the returned list SHALL have exactly one entry
- **AND** the entry SHALL have `id == "drift-submit-form"`, `category == "drift"`, `fixture == True`
- **AND** the entry SHALL have `variants == ["v1", "v2"]`

### Requirement: Drift suite pass gate
The drift suite SHALL be considered passing when every variant of every case in `category: drift` produces a `status` of `succeeded` or `unverified` in the eval results JSON.

All drift cases are `fixture: true`, so they SHALL run in CI without the `--live` flag and without live network access.

#### Scenario: Both variants pass with the same task
- **GIVEN** the eval runner runs `drift-submit-form` with variants `[v1, v2]`
- **WHEN** both sub-runs complete
- **THEN** the results JSON SHALL contain exactly two entries with ids `drift-submit-form-v1` and `drift-submit-form-v2`
- **AND** both entries SHALL have `status` in `{succeeded, unverified}`

### Requirement: drift/rename fixture pair for cache-invalidation proof

The repository SHALL include two HTML fixture files under `task2/tests/fixtures/drift/rename/`:

- `v1/index.html` — a minimal HTML page containing `<button>Submit</button>`. The button has accessible name "Submit" so L1 resolves it and `locate()` writes a cache entry with an AX fingerprint computed from `"button:Submit"`.
- `v2/index.html` — the same page where the button text has changed to `<button>Send</button>`. The selector written by v1 still resolves to one element on v2's DOM, but the AX fingerprint differs (accessible name is now "Send" not "Submit"). When `locate()` probes the cache with the v1 entry, it detects the fingerprint mismatch, calls `cache.invalidate()`, and falls through to L1 to resolve fresh.

Both files SHALL be static HTML served without any server-side processing.

#### Scenario: drift/rename/v1 fixture has accessible button "Submit"

- **WHEN** `task2/tests/fixtures/drift/rename/v1/index.html` is loaded
- **THEN** `page.get_by_role("button", name="Submit", exact=False).count()` SHALL equal `1`

#### Scenario: drift/rename/v2 fixture has accessible button "Send" (not "Submit")

- **WHEN** `task2/tests/fixtures/drift/rename/v2/index.html` is loaded
- **THEN** `page.get_by_role("button", name="Send", exact=False).count()` SHALL equal `1`
- **AND** `page.get_by_role("button", name="Submit", exact=False).count()` SHALL equal `0`

#### Scenario: Warm cache from v1 is invalidated when locate runs against v2

- **GIVEN** a `LocatorCache(path=":memory:")` warmed by `locate(v1_page, "Submit button", cache=cache)`
- **WHEN** `locate(v2_page, "Submit button", cache=cache)` is called
- **THEN** `cache.get(origin=..., intent="Submit button")` SHALL return `None` after the call (the v1 entry was invalidated)
- **AND** the call SHALL return a fresh `LocateResult` (not `tier="cache"`)
