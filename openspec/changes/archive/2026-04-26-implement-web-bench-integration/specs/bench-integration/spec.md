## ADDED Requirements

### Requirement: WebVoyager loader converts upstream task JSON to Case dicts
The loader `eval/bench/webvoyager_loader.py` SHALL parse a WebVoyager task JSON file (a list of objects with fields `id`, `web_name`, `ques`, `web`) and return a list of `Case`-compatible dicts accepted by `run_suite`.

Each output dict SHALL contain:
- `id`: string prefixed with `webvoyager-` followed by the upstream `id` field.
- `task`: string equal to the upstream `ques` field.
- `domain`: string equal to the upstream `web` field (used as the `goto` start URL).
- `category`: string equal to the upstream `web_name` field.
- `expect`: `{"schema": {"answer": "str"}, "validators": ["answer.nonempty"]}`.
- `budget`: `{"steps": 20, "usd": 0.25, "seconds": 120}`.
- `fixture`: `False` (benchmark cases are live; gated by `--live` at runner level).

#### Scenario: Loader parses vendored fixture sample
- **WHEN** `load_webvoyager("task2/tests/fixtures/benchmarks/webvoyager/tasks_sample.json")` is called
- **THEN** it returns a list of dicts equal in length to the fixture entries, each with keys `id`, `task`, `domain`, `category`, `expect`, `budget`, `fixture`

#### Scenario: Loader prefixes id with webvoyager-
- **WHEN** a fixture entry has upstream `id` value `"123"`
- **THEN** the output dict has `id == "webvoyager-123"`

#### Scenario: Loader maps ques to task
- **WHEN** a fixture entry has `ques` value `"Find the contact email"`
- **THEN** the output dict has `task == "Find the contact email"`

#### Scenario: Loader sets fixture to False
- **WHEN** any fixture entry is loaded
- **THEN** the output dict has `fixture == False`

### Requirement: Vendored benchmark fixture exists
The file `task2/tests/fixtures/benchmarks/webvoyager/tasks_sample.json` SHALL exist and contain 3–5 WebVoyager task entries, each with at minimum the fields `id`, `web_name`, `ques`, `web`.

#### Scenario: Fixture file is valid JSON
- **WHEN** `tasks_sample.json` is loaded with `json.load`
- **THEN** it returns a list of length 3–5 with no parse errors

#### Scenario: Each fixture entry has required fields
- **WHEN** iterating fixture entries
- **THEN** each entry has keys `id`, `web_name`, `ques`, `web`

### Requirement: Bench runner entry produces results JSON with existing shape
`scripts/bench.py`, invoked as `uv run python -m scripts.bench --suite webvoyager`, SHALL:
1. Load cases from the WebVoyager task source via the loader.
2. Call `run_suite` with those cases, delegating all loop/browser/LLM wiring to the existing machinery.
3. Write `eval/results/<ts>.json` with the same shape as `eval.py` (`run_at` string, `cases` list of `CaseResult` dicts with keys `id`, `status`, `steps`, `usd`, `l_tier_counts`, `validators`).
4. Exit non-zero if any case has a fail status (same `compute_exit_code` logic as `eval.py`).

#### Scenario: Smoke test — one case, stubbed browser and LLM, result JSON has correct shape
- **WHEN** `scripts.bench.loop` is patched to return a canned `RunResult(status="succeeded", result={"answer": "hello"}, ...)` and `Browser` + `LLMClient` are patched
- **THEN** calling `main(["--suite", "webvoyager"])` writes a `<ts>.json` file with `run_at` and `cases` containing at least one entry with all required `CaseResult` keys

#### Scenario: Bench runner skips live cases without --live
- **WHEN** `main(["--suite", "webvoyager"])` is called without `--live`
- **THEN** all benchmark cases (which have `fixture == False`) appear in results with `status == "skipped"`

#### Scenario: Bench runner includes cases with --live
- **WHEN** `main(["--suite", "webvoyager", "--live"])` is called with `loop` patched
- **THEN** benchmark cases are passed to `_run_case` and results appear with the patched status

#### Scenario: Bench runner honors EVAL_RESULTS_DIR env var
- **WHEN** env var `EVAL_RESULTS_DIR` is set to a custom temp path
- **THEN** the results JSON is written under that path

### Requirement: Bench runner reads LLM config from env vars
`scripts/bench.py` SHALL read `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` from environment variables (with the same defaults as `eval.py`) and SHALL NOT hardcode any provider URL.

#### Scenario: LLM_BASE_URL env var is honored
- **WHEN** `LLM_BASE_URL` is set to `"http://custom:9999/v1"` and `LLMClient` is patched
- **THEN** `LLMClient` is constructed with `base_url="http://custom:9999/v1"`
