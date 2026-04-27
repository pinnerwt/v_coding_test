## MODIFIED Requirements

### Requirement: Variant expansion

When a case dict has a `variants` key containing a non-empty list of strings, `run_suite` SHALL expand the case into one sub-run per variant before executing. For each variant `v`:

- The sub-run's `id` SHALL equal `<original-case-id>-<v>` (e.g. `drift-submit-form-v1`).
- The task, budget, expect, and fixture fields are inherited unchanged from the parent case.

When the case also has `shared_cache: true`, `run_suite` SHALL construct one `LocatorCache(path=":memory:")` instance for the parent case and pass it to each variant sub-run's `_run_case` call via a `cache` parameter. Each variant sub-run runs sequentially within the parent case so the cache state from v1 is visible when v2 runs.

When `shared_cache` is absent or `false`, no shared cache is constructed; each sub-run gets no cache.

The results JSON SHALL contain one `CaseResult` entry per variant sub-run (not one entry for the parent case). The total number of entries in the results JSON equals the sum of: non-variantized cases (count 1 each) plus variantized cases expanded to len(variants) entries each.

`_run_case` SHALL forward the `cache` argument it receives to `loop()` as `locator_cache=cache`. When `cache` is `None` (no shared cache configured), `locator_cache` SHALL not be passed (or passed as `None`) and the loop behaves with its current default.

#### Scenario: Drift case with two variants expands to two results entries

- **GIVEN** a drift case with `id: drift-submit-form`, `variants: [v1, v2]`, and `fixture: true`
- **WHEN** `run_suite` is called with this case and `live=False`
- **THEN** the results JSON `cases` array SHALL contain exactly two entries
- **AND** the first entry SHALL have `id == "drift-submit-form-v1"`
- **AND** the second entry SHALL have `id == "drift-submit-form-v2"`

#### Scenario: shared_cache=true passes same LocatorCache instance to both variant sub-runs

- **GIVEN** a case with `variants: [v1, v2]`, `fixture: true`, and `shared_cache: true`
- **AND** `_run_case` is instrumented to capture the `cache` argument it receives
- **WHEN** `run_suite` processes both variants
- **THEN** both `_run_case` calls SHALL receive the same `LocatorCache` object (identity `is` check)

#### Scenario: Non-variantized and variantized cases coexist in one suite run

- **GIVEN** a suite with two fixture cases: `fixture-heading` (no variants) and `drift-submit-form` (variants: v1, v2)
- **WHEN** `run_suite` is called with both cases and `live=False`
- **THEN** the results JSON `cases` array SHALL contain exactly three entries (1 + 2)

#### Scenario: Empty variants list runs as a single case with original id

- **GIVEN** a case with `variants: []`
- **WHEN** `run_suite` processes this case
- **THEN** the case SHALL produce a single results entry with the original `id`

#### Scenario: _run_case forwards cache to loop as locator_cache

- **GIVEN** `_run_case` is called with a non-None `cache` argument (a `LocatorCache` instance)
- **WHEN** `_run_case` invokes `loop()`
- **THEN** `loop()` SHALL be called with `locator_cache=cache` so the cache is active during the run

#### Scenario: _run_case with cache=None does not alter loop behavior

- **GIVEN** `_run_case` is called with `cache=None` (the default)
- **WHEN** `_run_case` invokes `loop()`
- **THEN** `loop()` SHALL be called without a non-None `locator_cache` argument
- **AND** loop behavior SHALL be identical to before this change

## ADDED Requirements

### Requirement: maintenance-drift-rename real-loop cache invalidation assertion

The test suite SHALL include a test that exercises the full `maintenance-drift-rename` cache invalidation path using a real (non-mocked) `loop()` with a real Playwright browser page but a mocked LLM. The test SHALL verify that the v2 case trace contains a `LocateEvent(cache_action="invalidate")` produced by the real `locate()` + `LocatorCache` interaction.

This test confirms that the cache forwarding from `_run_case` → `loop()` → `locate()` works end-to-end and that `maintenance-drift-rename` actually exercises cache continuity in production-path code, not just through unit-test mocks.

#### Scenario: maintenance-drift-rename v2 produces invalidation event via real loop

- **GIVEN** a real Playwright browser (via `playwright_chromium` fixture) serving `tests/fixtures/drift/rename/v1/index.html` for v1 and `tests/fixtures/drift/rename/v2/index.html` for v2
- **AND** a mocked LLM that emits `read(intent="Submit button")` and then `done(result={}, evidence={url, text_snippet})` for both v1 and v2 runs
- **AND** a shared `LocatorCache(path=":memory:")` passed to both runs via `loop(..., locator_cache=cache)`
- **WHEN** the v1 run completes (cache warmed with "Submit" fingerprint) and the v2 run completes (fingerprint mismatch detected)
- **THEN** `_aggregate_diagnostics(writer_v2, run_id_v2)` SHALL return `cache_events["invalidations"] >= 1`
- **AND** both runs SHALL complete with `status` in `{"succeeded", "unverified"}`
