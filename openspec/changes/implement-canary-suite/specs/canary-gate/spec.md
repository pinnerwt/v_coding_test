## ADDED Requirements

### Requirement: canary_gate CLI module

`task2/scripts/canary_gate.py` SHALL be a runnable Python module invokable as `uv run python -m scripts.canary_gate --results <path>` from the `task2/` directory. The module SHALL accept one required CLI argument:

- `--results <path>` — path to a `results.json` file produced by `scripts.benchmark` or `scripts.eval`.

The module SHALL read the results file, identify all case entries where `case.get("canary", False)` is truthy, and apply the following gate logic:

1. If no canary cases are found in the results file, the gate SHALL print a notice to stdout (e.g. `"canary-gate: no canary cases found in results; gate is a no-op"`) and exit 0.
2. If any canary case has `status` NOT in `{"succeeded", "unverified"}` (including `"skipped"`, `"failed"`, `"blocked"`, `"timeout"`), the gate SHALL print a failure message to stdout listing the failing canary case ids and their statuses, then exit with code 1.
3. If all canary cases have `status` in `{"succeeded", "unverified"}` but at least one non-canary case has a non-passing, non-skipped status (`"failed"`, `"blocked"`, or `"timeout"`), the gate SHALL print a warning to stdout (e.g. `"WARNING: non-canary regressions detected: <ids>"`) and exit with code 0.
4. If all canary cases pass and all non-canary non-skipped cases also pass (or there are none), the gate SHALL print a success message to stdout and exit with code 0.

The module SHALL import `PASS_STATUSES` from `scripts.eval` to define "passing". The set SHALL be `{"succeeded", "unverified"}`. No other status is considered passing for canary purposes.

The module SHALL NOT import Playwright, LLMClient, or any browser-related dependency. It SHALL be pure-Python with stdlib-only dependencies (plus `scripts.eval` for `PASS_STATUSES`).

#### Scenario: One canary failed — gate exits 1

- **GIVEN** a `results.json` with two cases: `fixture-heading` (`canary: true`, `status: "failed"`) and `canary-read-h1` (`canary: true`, `status: "succeeded"`)
- **WHEN** `canary_gate.main(["--results", "<path>"])` is called
- **THEN** the process SHALL exit with code 1
- **AND** stdout SHALL contain the string `"fixture-heading"` identifying the failing canary

#### Scenario: All canaries pass, non-canary failed — gate exits 0 with warning

- **GIVEN** a `results.json` with: `fixture-heading` (`canary: true`, `status: "succeeded"`), `canary-read-h1` (`canary: true`, `status: "succeeded"`), and `live-search-extract` (`canary: false`, `status: "failed"`)
- **WHEN** `canary_gate.main(["--results", "<path>"])` is called
- **THEN** the process SHALL exit with code 0
- **AND** stdout SHALL contain the word `"WARNING"` and reference `"live-search-extract"`

#### Scenario: All canaries pass, all non-canaries pass — gate exits 0 cleanly

- **GIVEN** a `results.json` where all cases with `canary: true` have `status: "succeeded"` and no non-canary case has a failing status
- **WHEN** `canary_gate.main(["--results", "<path>"])` is called
- **THEN** the process SHALL exit with code 0
- **AND** stdout SHALL NOT contain the word `"WARNING"`

#### Scenario: Canary case skipped — gate exits 1

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

### Requirement: Canary case YAML files

The repository SHALL include two case YAML files tagged as canary:

1. `task2/eval/cases/fixture-heading.yaml` — existing file; `canary: true` and `fixture_url` (a `data:text/html,...` URL containing a single `<h1>`) SHALL be added.
2. `task2/eval/cases/canary-read-h1.yaml` — new file. It SHALL have:
   - `id: canary-read-h1`
   - `domain: fixture`
   - `category: read-and-summarize`
   - `canary: true`
   - `fixture: true`
   - `task`: a natural-language instruction to read the page's H1 heading and return it as `title`
   - `expect.schema: { title: str }`
   - `expect.validators: [title.nonempty]`
   - `fixture_url`: a `data:text/html,...` URL embedding a minimal page with a single `<h1>` element so the agent has content to read without external resources
   - `budget: { steps: 5, usd: 0.02, seconds: 30 }` (matches the other fixture canaries; the gate trades aspirational tightness for must-always-pass reliability under the 27B model)

Both cases SHALL be `fixture: true` so they run in CI without `--live`. `fixture-count.yaml` is intentionally left non-canary because its list-extraction path hits an unrelated locate-engine `IntentParseError`; it will be revisited in a follow-up ticket.

#### Scenario: fixture-heading.yaml carries canary: true after this change

- **WHEN** `task2/eval/cases/fixture-heading.yaml` is loaded via `scripts.eval.load_cases`
- **THEN** the returned case dict SHALL have `canary == True`

#### Scenario: canary-read-h1.yaml loads as a valid fixture canary case

- **WHEN** `task2/eval/cases/canary-read-h1.yaml` is loaded via `scripts.eval.load_cases`
- **THEN** the returned case dict SHALL have `canary == True`, `fixture == True`, and `budget["steps"] == 5`

### Requirement: canary field serialized into results.json

When `scripts.eval.run_suite` or `scripts.benchmark.main` produces a `results.json`, each case entry SHALL include a `canary` boolean field. Its value SHALL be the `canary` field from the case dict (defaulting to `False` when absent in the YAML).

`CaseResult` (in `scripts/eval.py`) SHALL gain a `canary: bool = False` field. `AggregatedCaseResult` (in `scripts/benchmark.py`) SHALL gain a `canary: bool = False` field. Both dataclasses SHALL serialize `canary` via `dataclasses.asdict()`.

`run_suite` SHALL pass `canary=case.get("canary", False)` when constructing each `CaseResult`. `aggregate_repeats` SHALL pass `canary=case.get("canary", False)` when constructing each `AggregatedCaseResult`.

`canary_gate.py` SHALL read `case.get("canary", False)` from the parsed results JSON, treating a missing field as `False` for backward compatibility with results files written before this change.

#### Scenario: Canary case appears with canary: true in results JSON

- **GIVEN** `fixture-heading.yaml` has `canary: true`
- **AND** `run_suite` processes it
- **WHEN** the results JSON is parsed
- **THEN** the `fixture-heading` case entry SHALL have `"canary": true`

#### Scenario: Non-canary case appears with canary: false in results JSON

- **GIVEN** a case YAML file with no `canary` field
- **AND** `run_suite` processes it
- **WHEN** the results JSON is parsed
- **THEN** the case entry SHALL have `"canary": false`

#### Scenario: canary_gate reads missing canary field as false (backward compat)

- **GIVEN** a legacy `results.json` whose case entries have no `canary` key
- **WHEN** `canary_gate.main(["--results", "<path>"])` is called
- **THEN** all cases are treated as non-canary and the gate exits 0 with a no-canary notice

### Requirement: CI workflow canary gate step

`.github/workflows/task2-benchmark.yml` SHALL add a new step named "Canary gate" after the "Verify benchmark recorded for branch" step. The step SHALL:

1. Run unconditionally (not gated on `github.event_name`).
2. Execute `uv run python -m scripts.canary_gate --results benchmark/${SAFE_BRANCH}/results.json` from the `task2/` working directory, where `SAFE_BRANCH` is computed the same way as in the existing "Post diff as PR comment" step.
3. Propagate the exit code: exit 1 from `canary_gate.py` SHALL cause the CI job to fail and block merge.
4. Print stdout from `canary_gate.py` to the workflow log so reviewers can see which canary cases failed.

The step SHALL NOT re-run the benchmark; it SHALL read the already-committed `results.json` from the branch.

#### Scenario: CI job fails when a canary case is failed in results.json

- **GIVEN** a branch whose committed `results.json` has a case with `canary: true` and `status: "failed"`
- **WHEN** the "Canary gate" CI step runs
- **THEN** the step exits non-zero
- **AND** the CI job fails, blocking merge

#### Scenario: CI job passes when all canaries pass even if non-canaries failed

- **GIVEN** a branch whose committed `results.json` has all canary cases with `status: "succeeded"` but a non-canary case with `status: "failed"`
- **WHEN** the "Canary gate" CI step runs
- **THEN** the step exits 0
- **AND** the CI job does not fail on account of the non-canary regression

### Requirement: Pure-Python unit tests for canary gate

`task2/tests/test_canary_gate.py` SHALL contain unit tests for the gate logic. Tests SHALL use synthetic `results.json` dicts (plain Python dicts, written to `tmp_path` files via `pytest`'s `tmp_path` fixture). Tests SHALL NOT call the browser, LLM, or any live network. Tests SHALL NOT use `unittest.mock.patch` on `_run_case` or `loop` — the gate is tested purely by varying the input JSON.

Required test cases:

- **Test A — Canary failed → gate exits 1**: Construct a results dict with one canary case (`canary: true`, `status: "failed"`). Assert `canary_gate.main(["--results", str(path)])` raises `SystemExit(1)` (or returns 1).
- **Test B — All canaries pass, non-canary failed → gate exits 0**: Construct a results dict with two canary cases (both `status: "succeeded"`) and one non-canary case (`status: "failed"`). Assert exit code is 0 and output contains `"WARNING"`.
- **Test C — No canary cases → gate exits 0 with notice**: Construct a results dict with no `canary: true` cases. Assert exit code is 0.
- **Test D — Canary skipped → gate exits 1**: Construct a results dict with one canary case (`status: "skipped"`, `skip_reason: "live_disabled"`). Assert exit code is 1.
- **Test E — All pass including canaries → gate exits 0 cleanly**: Construct a results dict with two canary cases (both `status: "succeeded"`) and one non-canary case (`status: "succeeded"`). Assert exit code is 0 and output does NOT contain `"WARNING"`.

#### Scenario: Test A — canary failed produces exit 1

- **GIVEN** a synthetic results file with `{"cases": [{"id": "fixture-heading", "canary": true, "status": "failed"}]}`
- **WHEN** `canary_gate.main(["--results", str(path)])` is called
- **THEN** the exit code SHALL be 1

#### Scenario: Test B — all canaries pass, non-canary failed produces exit 0 with warning

- **GIVEN** a synthetic results file with two canary-passing cases and one non-canary-failing case
- **WHEN** `canary_gate.main(["--results", str(path)])` is called
- **THEN** the exit code SHALL be 0
- **AND** the captured stdout SHALL contain `"WARNING"`

#### Scenario: Test C — no canary cases produces exit 0 with notice

- **GIVEN** a synthetic results file with cases that all have `canary: false` (or no `canary` key)
- **WHEN** `canary_gate.main(["--results", str(path)])` is called
- **THEN** the exit code SHALL be 0

#### Scenario: Test D — canary skipped produces exit 1

- **GIVEN** a synthetic results file with `{"cases": [{"id": "fixture-heading", "canary": true, "status": "skipped"}]}`
- **WHEN** `canary_gate.main(["--results", str(path)])` is called
- **THEN** the exit code SHALL be 1

#### Scenario: Test E — all pass produces exit 0 without warning

- **GIVEN** a synthetic results file with all cases (canary and non-canary) having `status: "succeeded"`
- **WHEN** `canary_gate.main(["--results", str(path)])` is called
- **THEN** the exit code SHALL be 0
- **AND** the captured stdout SHALL NOT contain `"WARNING"`
