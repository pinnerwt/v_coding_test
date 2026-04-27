## MODIFIED Requirements

### Requirement: Case YAML schema

Each eval case SHALL be expressed as a YAML file under `task2/eval/cases/` with the following fields:

- `id: str` — unique kebab-case identifier for the case (used as the key in results JSON).
- `domain: str` — the target domain or fixture identifier (e.g. `fixture`, `arxiv.org`).
- `category: str` — one of: `search-and-extract`, `form-filling`, `multi-page-navigation`, `conditional-pick`, `read-and-summarize`, `drift`, `correction`.
- `task: str` — the natural-language task string passed verbatim to the agent loop.
- `expect.schema: dict` — the expected output key types. Stored and forwarded to the loop; full JSONSchema validation is deferred.
- `expect.validators: list[str]` — list of validator expressions evaluated against the loop's `result` dict. Supported vocabulary: `<key>.nonempty` and `<key>.len_gte: <N>`.
- `budget.steps: int` — maximum agent loop steps for this case.
- `budget.usd: float` — maximum USD spend for this case.
- `budget.seconds: int` — wall-clock timeout in seconds.
- `fixture: bool` (optional, default `false`) — when `true`, the case is CI-safe and runs without `--live`.
- `variants: list[str]` (optional) — when present, the runner expands this case into one sub-run per variant.
- `shared_cache: bool` (optional, default `false`) — when `true` and `variants` is present, the runner constructs a single `LocatorCache(path=":memory:")` shared across all variant sub-runs of this case and passes it to each `loop()` call. When `false` or absent, each sub-run gets no shared cache (the default behaviour).

#### Scenario: Valid case YAML loads without error

- **WHEN** `task2/eval/cases/fixture-heading.yaml` is loaded via `scripts/eval.py`
- **THEN** the resulting case object SHALL have `id`, `domain`, `category`, `task`, `expect.schema`, `expect.validators`, and `budget` fields populated

#### Scenario: Case missing required field raises on load

- **WHEN** a YAML file is missing the `task` field
- **THEN** the loader SHALL raise a `ValueError` identifying the missing field and the file path

#### Scenario: fixture flag controls CI gating

- **WHEN** `--live` is absent and a case has `fixture: true`
- **THEN** the runner SHALL include the case in the run
- **WHEN** `--live` is absent and a case does NOT have `fixture: true`
- **THEN** the runner SHALL skip the case

#### Scenario: variants field is optional and backward-compatible

- **WHEN** a YAML case file does not contain a `variants` key
- **THEN** `load_cases` SHALL succeed and the case SHALL run as a single unit with its original `id`

#### Scenario: shared_cache field is optional and backward-compatible

- **WHEN** a YAML case file does not contain a `shared_cache` key
- **THEN** `load_cases` SHALL succeed and the case SHALL run with `shared_cache` defaulting to `false`

### Requirement: Variant expansion with optional shared cache

When a case dict has a `variants` key containing a non-empty list of strings, `run_suite` SHALL expand the case into one sub-run per variant. For each variant `v`:

- The sub-run's `id` SHALL equal `<original-case-id>-<v>`.
- The task, budget, expect, and fixture fields are inherited unchanged from the parent case.

When the case also has `shared_cache: true`, `run_suite` SHALL construct one `LocatorCache(path=":memory:")` instance for the parent case and pass it to each variant sub-run's `_run_case` call via a `cache` parameter. Each variant sub-run runs sequentially within the parent case so the cache state from v1 is visible when v2 runs.

When `shared_cache` is absent or `false`, no shared cache is constructed; each sub-run gets no cache.

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
