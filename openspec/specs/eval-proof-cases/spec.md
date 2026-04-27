# eval-proof-cases Specification

## Purpose
TBD - created by archiving change implement-self-correction-proof. Update Purpose after archive.

## Requirements

### Requirement: correction-l1-miss-l2-hit fixture case

The repository SHALL include `task2/eval/cases/correction-l1-miss-l2-hit.yaml` — a fixture-backed eval case (`fixture: true`, `category: correction`) whose only success path requires the agent to escalate from L1 to L2 (L1 returns zero matches; L2 resolves via the button taxonomy CSS selector).

The supporting HTML fixture at `task2/tests/fixtures/correction_l1_miss.html` SHALL contain a submit control with **no accessible role and no accessible name** — specifically a `<div class="btn">Submit</div>` element — so that `page.get_by_role("button", ...)` returns zero results (L1 misses) and `page.locator('[class*="btn"]').filter(has_text="Submit")` returns one result (L2 hits).

#### Scenario: correction-l1-miss-l2-hit.yaml exists and is valid

- **WHEN** `task2/eval/cases/correction-l1-miss-l2-hit.yaml` is loaded via `load_cases`
- **THEN** it SHALL parse without error
- **AND** have `fixture: true`, `category: "correction"`, and a non-empty `task` string
- **AND** have `budget.steps >= 3` to allow for the locate escalation step

#### Scenario: correction_l1_miss.html forces L1 miss and L2 hit

- **GIVEN** a Playwright page loaded with `tests/fixtures/correction_l1_miss.html`
- **WHEN** `page.get_by_role("button", name="Submit", exact=False).count()` is evaluated
- **THEN** the count SHALL equal `0` (L1 would miss)
- **WHEN** `page.locator('[class*="btn"]').filter(has_text="Submit").count()` is evaluated
- **THEN** the count SHALL equal `1` (L2 resolves)

### Requirement: correction-replan fixture case

The repository SHALL include `task2/eval/cases/correction-replan.yaml` — a fixture-backed eval case (`fixture: true`, `category: correction`) whose only success path requires the supervisor to `halt` (because a `read` locate attempt fails beyond `max_attempts`) and then fire the one-shot `replan` path in `loop.py`.

The supporting HTML fixture at `task2/tests/fixtures/correction_replan_deadend.html` SHALL be a minimal page with a heading "Dead end" and **no actionable elements**, so any `read` intent targeting an element returns a `LocatorMiss` that the supervisor escalates and then halts on.

In the eval test for this case, `loop()` SHALL be mocked so that:
- On the first call to `Supervisor.handle()` the policy is `"halt"`.
- `plan_module.replan()` returns a `Plan` whose single step directs the agent to call `done`.
- The case eventually returns `status="succeeded"`.

The assertion for this case is `CaseResult.replans == 1 and CaseResult.status == "succeeded"`.

#### Scenario: correction-replan.yaml exists and is valid

- **WHEN** `task2/eval/cases/correction-replan.yaml` is loaded via `load_cases`
- **THEN** it SHALL parse without error
- **AND** have `fixture: true`, `category: "correction"`, and a non-empty `task` string

#### Scenario: correction_replan_deadend.html has no actionable elements

- **GIVEN** a Playwright page loaded with `tests/fixtures/correction_replan_deadend.html`
- **WHEN** `page.get_by_role("button").count()` is evaluated
- **THEN** the count SHALL equal `0`
- **WHEN** `page.get_by_role("textbox").count()` is evaluated
- **THEN** the count SHALL equal `0`

#### Scenario: eval assertion for replan case — replans==1 and status succeeded

- **GIVEN** `correction-replan` case run via `run_suite` with loop mocked to emit one `PlanEvent(reason="replan")` and return `status="succeeded"`
- **WHEN** the resulting `CaseResult` is inspected
- **THEN** `CaseResult.replans` SHALL equal `1`
- **AND** `CaseResult.status` SHALL equal `"succeeded"`

#### Scenario: removing replan path causes replan assertion to fail

- **GIVEN** the replan path in `loop.py` is disabled (e.g. `supervisor.replan_used` forced `True` before the halt check, so replan is never called)
- **WHEN** the `correction-replan` eval case runs
- **THEN** `CaseResult.replans` SHALL equal `0`
- **AND** the assertion `CaseResult.replans == 1` SHALL fail

### Requirement: maintenance-drift-rename fixture case

The repository SHALL include `task2/eval/cases/maintenance-drift-rename.yaml` — a fixture-backed eval case (`fixture: true`, `category: drift`, `variants: [v1, v2]`, `shared_cache: true`) whose success path for v2 requires the locator cache to invalidate a warm v1 entry because the button's accessible name changed between variants.

Two supporting HTML fixtures SHALL exist:
- `task2/tests/fixtures/drift/rename/v1/index.html` — a page with `<button>Submit</button>` (accessible name "Submit"; L1 resolves; cache writes entry with AX fingerprint for "Submit").
- `task2/tests/fixtures/drift/rename/v2/index.html` — the same page where the button text has changed to `<button>Send</button>` (accessible name "Send"). When the v1 cache entry is probed for v2's DOM, the selector still resolves to one element but the AX fingerprint differs (the accessible name changed from "Submit" to "Send"), so `locate()` invalidates the entry and falls through to L1 to resolve fresh.

`run_suite` SHALL accept a `shared_cache: true` field in the case dict and, when present, construct a single `LocatorCache(path=":memory:")` shared across all variant sub-runs of that case. Each variant's `_run_case` call receives the shared cache object rather than constructing a new one.

The assertion for v2 is `CaseResult.cache_events["invalidations"] >= 1 and CaseResult.status == "succeeded"`.

#### Scenario: maintenance-drift-rename.yaml exists, is valid, and has variants and shared_cache

- **WHEN** `task2/eval/cases/maintenance-drift-rename.yaml` is loaded via `load_cases`
- **THEN** it SHALL parse without error
- **AND** have `fixture: true`, `category: "drift"`, `variants == ["v1", "v2"]`, and `shared_cache: true`

#### Scenario: drift/rename/v1 resolves at L1_ax

- **GIVEN** a Playwright page loaded with `tests/fixtures/drift/rename/v1/index.html`
- **WHEN** `locate(page, "Submit button")` is called
- **THEN** `result.tier` SHALL equal `"L1_ax"`

#### Scenario: drift/rename/v2 triggers cache invalidation when cache is warm from v1

- **GIVEN** a `LocatorCache` that has been warmed by a `locate(v1_page, "Submit button", cache=cache)` call storing an entry with `ax_fingerprint` for accessible name "Submit"
- **WHEN** `locate(v2_page, "Submit button", cache=cache)` is called (v2 has `<button>Send</button>`)
- **THEN** the selector still resolves (one element) but the AX fingerprint differs
- **AND** `cache.invalidate(...)` SHALL be called (the cache entry is removed)
- **AND** `locate()` SHALL fall through to the L1–L4 ladder and return a fresh `LocateResult`

#### Scenario: eval assertion for drift-rename v2 — cache_events.invalidations >= 1 and status succeeded

- **GIVEN** `maintenance-drift-rename` v2 case run via `run_suite` with a shared warm cache and a Playwright-backed or mocked `loop()` that traverses the invalidation path
- **WHEN** the resulting `CaseResult` for `maintenance-drift-rename-v2` is inspected
- **THEN** `CaseResult.cache_events["invalidations"]` SHALL be `>= 1`
- **AND** `CaseResult.status` SHALL equal `"succeeded"`
