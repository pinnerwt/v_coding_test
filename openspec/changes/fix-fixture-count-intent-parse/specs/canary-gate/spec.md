## MODIFIED Requirements

### Requirement: Canary case YAML files

The repository SHALL include three case YAML files tagged as canary:

1. `task2/eval/cases/fixture-heading.yaml` — existing file; `canary: true` and `fixture_url` (a `data:text/html,...` URL containing a single `<h1>`) SHALL be present.
2. `task2/eval/cases/canary-read-h1.yaml` — existing file. It SHALL have:
   - `id: canary-read-h1`
   - `domain: fixture`
   - `category: read-and-summarize`
   - `canary: true`
   - `fixture: true`
   - `task`: a natural-language instruction to read the page's H1 heading and return it as `title`
   - `expect.schema: { title: str }`
   - `expect.validators: [title.nonempty]`
   - `fixture_url`: a `data:text/html,...` URL embedding a minimal page with a single `<h1>` element so the agent has content to read without external resources
   - `budget: { steps: 5, usd: 0.02, seconds: 30 }`
3. `task2/eval/cases/fixture-count.yaml` — existing file. `canary: true` SHALL be added to it now that the `IntentParseError` for `list`/`listitem` role tokens is resolved. It SHALL have:
   - `id: fixture-count`
   - `domain: fixture`
   - `category: search-and-extract`
   - `canary: true`
   - `fixture: true`
   - `task`: an instruction to read all list items and return them as `items`
   - `expect.schema: { items: list[str] }`
   - `expect.validators: [items.len_gte: 1]`
   - `fixture_url`: a `data:text/html,...` URL with a `<ul>` containing at least three `<li>` elements
   - `budget: { steps: 5, usd: 0.05, seconds: 30 }`

All three cases SHALL be `fixture: true` so they run in CI without `--live`.

#### Scenario: fixture-heading.yaml carries canary: true

- **WHEN** `task2/eval/cases/fixture-heading.yaml` is loaded via `scripts.eval.load_cases`
- **THEN** the returned case dict SHALL have `canary == True`

#### Scenario: canary-read-h1.yaml loads as a valid fixture canary case

- **WHEN** `task2/eval/cases/canary-read-h1.yaml` is loaded via `scripts.eval.load_cases`
- **THEN** the returned case dict SHALL have `canary == True`, `fixture == True`, and `budget["steps"] == 5`

#### Scenario: fixture-count.yaml carries canary: true after this change

- **WHEN** `task2/eval/cases/fixture-count.yaml` is loaded via `scripts.eval.load_cases`
- **THEN** the returned case dict SHALL have `canary == True` and `fixture == True`

### Requirement: canary_gate CLI module

`task2/scripts/canary_gate.py` SHALL be a runnable Python module invokable as `uv run python -m scripts.canary_gate --results <path>` from the `task2/` directory. The module SHALL accept one required CLI argument:

- `--results <path>`: path to a `results.json` file produced by `scripts.eval.run_suite` or `scripts.benchmark.main`.

The module SHALL read the results file, identify all case entries where `case.get("canary", False)` is truthy, and apply the following gate logic:

1. If no canary cases are found in the results file, the gate SHALL print a notice to stdout (e.g. `"canary-gate: no canary cases found in results; gate is a no-op"`) and exit 0.
2. If any canary case has `status` NOT in `{"succeeded", "unverified"}` (including `"skipped"`, `"failed"`, `"blocked"`, `"timeout"`), the gate SHALL print a failure message to stdout listing the failing canary case ids and their statuses, then exit with code 1.
3. If all canary cases have `status` in `{"succeeded", "unverified"}` but at least one non-canary case has a non-passing, non-skipped status (`"failed"`, `"blocked"`, or `"timeout"`), the gate SHALL print a warning to stdout (e.g. `"WARNING: non-canary regressions detected: <ids>"`) and exit with code 0.
4. If all canary cases pass and all non-canary non-skipped cases also pass (or there are none), the gate SHALL print a success message to stdout and exit with code 0.

The module SHALL import `PASS_STATUSES` from `scripts.eval` to define "passing". The set SHALL be `{"succeeded", "unverified"}`. No other status is considered passing for canary purposes.

The canary set now comprises three cases: `fixture-heading`, `canary-read-h1`, and `fixture-count`. The gate logic is unchanged; it reads the `canary` field dynamically from results JSON, so no code change is required to support the third canary.

#### Scenario: One canary failed — gate exits 1

- **GIVEN** a `results.json` with two cases: `fixture-heading` (`canary: true`, `status: "failed"`) and `canary-read-h1` (`canary: true`, `status: "succeeded"`)
- **WHEN** `canary_gate.main(["--results", "<path>"])` is called
- **THEN** the process SHALL exit with code 1
- **AND** stdout SHALL contain the string `"fixture-heading"` identifying the failing canary

#### Scenario: All canaries pass, non-canary failed — gate exits 0 with warning

- **GIVEN** a `results.json` with: `fixture-heading` (`canary: true`, `status: "succeeded"`), `canary-read-h1` (`canary: true`, `status: "succeeded"`), `fixture-count` (`canary: true`, `status: "succeeded"`), and `live-search-extract` (`canary: false`, `status: "failed"`)
- **WHEN** `canary_gate.main(["--results", "<path>"])` is called
- **THEN** the process SHALL exit with code 0
- **AND** stdout SHALL contain a warning mentioning `"live-search-extract"`

#### Scenario: All three canaries pass, no non-canary failures — gate exits 0 with success message

- **GIVEN** a `results.json` where all cases with `canary: true` (including `fixture-count`) have `status: "succeeded"` and no non-canary case has a failing status
- **WHEN** `canary_gate.main(["--results", "<path>"])` is called
- **THEN** the process SHALL exit with code 0
- **AND** stdout SHALL contain a success message

#### Scenario: Canary is skipped — gate exits 1

- **GIVEN** a `results.json` with `fixture-heading` (`canary: true`, `status: "skipped"`)
- **WHEN** `canary_gate.main(["--results", "<path>"])` is called
- **THEN** the process SHALL exit with code 1
- **AND** stdout SHALL identify `"fixture-heading"` as a failing canary (skipped counts as non-passing)

#### Scenario: No canary cases in results — gate exits 0 with notice

- **GIVEN** a `results.json` where no case has `canary: true`
- **WHEN** `canary_gate.main(["--results", "<path>"])` is called
- **THEN** the process SHALL exit with code 0
- **AND** stdout SHALL contain a notice indicating no canary cases were found

#### Scenario: Missing --results argument causes error exit

- **WHEN** `canary_gate.main([])` is called without `--results`
- **THEN** the process SHALL exit with a non-zero code and print a usage error
