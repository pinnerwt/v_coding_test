## MODIFIED Requirements

### Requirement: Case YAML schema
Each eval case SHALL be expressed as a YAML file under `task2/eval/cases/` with the following fields:

- `id: str` — unique kebab-case identifier for the case (used as the key in results JSON).
- `domain: str` — the target domain or fixture identifier (e.g. `fixture`, `arxiv.org`).
- `category: str` — one of: `search-and-extract`, `form-filling`, `multi-page-navigation`, `conditional-pick`, `read-and-summarize`, `drift`.
- `task: str` — the natural-language task string passed verbatim to the agent loop.
- `expect.schema: dict` — the expected output key types (e.g. `{ title: str, authors: list[str] }`). Stored and forwarded to the loop; full JSONSchema validation is deferred.
- `expect.validators: list[str]` — list of validator expressions evaluated against the loop's `result` dict. Supported vocabulary for this ticket: `<key>.nonempty` and `<key>.len_gte: <N>`.
- `budget.steps: int` — maximum agent loop steps for this case.
- `budget.usd: float` — maximum USD spend for this case.
- `budget.seconds: int` — wall-clock timeout in seconds.
- `fixture: bool` (optional, default `false`) — when `true`, the case is CI-safe and runs without `--live`.
- `variants: list[str]` (optional) — when present, the runner expands this case into one sub-run per variant. Each variant value is a short identifier (e.g. `"v1"`, `"v2"`) appended to the case `id` with a hyphen to form the sub-run id. If absent or empty, the case runs as a single run with its original `id`.

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

#### Scenario: variants field parsed as list of strings
- **WHEN** `task2/eval/cases/drift-submit-form.yaml` is loaded
- **THEN** the returned dict SHALL have `variants == ["v1", "v2"]`

### Requirement: Variant expansion
When a case dict has a `variants` key containing a non-empty list of strings, `run_suite` SHALL expand the case into one sub-run per variant before executing. For each variant `v`:

- The sub-run's `id` SHALL equal `<original-case-id>-<v>` (e.g. `drift-submit-form-v1`).
- The task, budget, expect, and fixture fields are inherited unchanged from the parent case.

The results JSON SHALL contain one `CaseResult` entry per variant sub-run (not one entry for the parent case). The total number of entries in the results JSON equals the sum of: non-variantized cases (count 1 each) plus variantized cases expanded to len(variants) entries each.

#### Scenario: Drift case with two variants expands to two results entries
- **GIVEN** a drift case with `id: drift-submit-form`, `variants: [v1, v2]`, and `fixture: true`
- **WHEN** `run_suite` is called with this case and `live=False`
- **THEN** the results JSON `cases` array SHALL contain exactly two entries
- **AND** the first entry SHALL have `id == "drift-submit-form-v1"`
- **AND** the second entry SHALL have `id == "drift-submit-form-v2"`

#### Scenario: Non-variantized and variantized cases coexist in one suite run
- **GIVEN** a suite with two fixture cases: `fixture-heading` (no variants) and `drift-submit-form` (variants: v1, v2)
- **WHEN** `run_suite` is called with both cases and `live=False`
- **THEN** the results JSON `cases` array SHALL contain exactly three entries (1 + 2)

#### Scenario: Empty variants list runs as a single case with original id
- **GIVEN** a case with `variants: []`
- **WHEN** `run_suite` processes this case
- **THEN** the case SHALL produce a single results entry with the original `id`

### Requirement: Results JSON schema
The eval runner SHALL write a results JSON to `task2/eval/results/<ts>.json` (where `<ts>` is `YYYYMMDD_HHMMSS` UTC) after running the suite. The JSON SHALL have the following top-level shape:

```json
{
  "run_at": "<iso8601-utc>",
  "cases": [
    {
      "id": "<case-id>",
      "status": "<succeeded|unverified|failed|blocked|timeout|skipped>",
      "steps": <int>,
      "usd": <float>,
      "l_tier_counts": { "<tier-name>": <int>, ... },
      "validators": [
        { "name": "<validator-expr>", "ok": <bool> }
      ]
    }
  ]
}
```

- `run_at`: ISO 8601 UTC timestamp of when the suite run started.
- `cases`: ordered list of per-case results, one entry per case regardless of skip status. For variantized cases, the entry `id` is the expanded sub-run id (e.g. `drift-submit-form-v1`), not the parent case id.
- `status`: one of `succeeded`, `unverified`, `failed`, `blocked`, `timeout`, `skipped`. `skipped` is used when a non-fixture case is excluded because `--live` was not passed.
- `steps`: number of agent loop steps consumed (integer ≥ 0; 0 for skipped cases).
- `usd`: estimated USD cost of the case run (float ≥ 0.0; 0.0 for skipped cases or when cost tracking is not yet wired).
- `l_tier_counts`: dict mapping L-tier name (e.g. `"L1_ax"`, `"L2_dom"`, `"L3_rerank"`, `"L4_vision"`, `"cache"`) to the integer number of locate attempts that resolved at that tier for this case. Empty dict `{}` is valid.
- `validators`: list of validator results, one per entry in `expect.validators`. Empty list `[]` is valid when `expect.validators` is empty or the case was skipped.

#### Scenario: Results JSON exists after runner completes
- **WHEN** `scripts/eval.py` is invoked and all cases complete (or are skipped)
- **THEN** a JSON file SHALL exist at `eval/results/<ts>.json` relative to `task2/`

#### Scenario: Results JSON contains one entry per case
- **WHEN** the suite has 2 cases and `--live` is absent and both have `fixture: true`
- **THEN** the `cases` array in the results JSON SHALL have exactly 2 entries

#### Scenario: Skipped case has status skipped and zero steps
- **WHEN** a case has no `fixture: true` and `--live` is absent
- **THEN** the case entry in results JSON SHALL have `status: "skipped"`, `steps: 0`, `usd: 0.0`, `l_tier_counts: {}`, `validators: []`

#### Scenario: Results JSON is valid JSON
- **WHEN** the results file is written
- **THEN** `json.loads(results_file.read_text())` SHALL succeed without error

#### Scenario: l_tier_counts is always a dict
- **WHEN** a case completes with no locate calls (e.g. the task calls `done` immediately)
- **THEN** `l_tier_counts` SHALL be `{}` (empty dict), NOT `null` or absent

### Requirement: Eval runner CLI
The system SHALL expose `scripts/eval.py` as a runnable script from `task2/` via `uv run python scripts/eval.py`. The CLI SHALL accept the following optional flags:

- `--live`: include non-fixture (live) cases in the run. Without this flag, only cases with `fixture: true` are executed.
- `--case <id>`: run only the case with the given `id`. Can be combined with `--live`.

The runner SHALL print per-case progress to stdout as each case completes (format: `[PASS|FAIL|SKIP] <id> (<steps> steps, $<usd>)`). After the suite completes, it SHALL print the path to the written results JSON.

The runner SHALL exit with code 0 if all executed cases have `status` in `{succeeded, unverified, skipped}`. It SHALL exit with code 1 if any executed case has `status` in `{failed, blocked, timeout}`.

The runner SHALL NOT hardcode any LLM provider URL. `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY` are read from env (same defaults as `agent/llm.py`).

#### Scenario: Runner completes and writes results file
- **WHEN** `uv run python scripts/eval.py` is invoked from `task2/` with only fixture cases present
- **THEN** the runner SHALL execute all fixture cases, print progress, and write a results JSON

#### Scenario: --case flag runs only the named case
- **WHEN** `uv run python scripts/eval.py --case fixture-heading` is invoked
- **THEN** the runner SHALL execute only the `fixture-heading` case and write a results JSON with exactly 1 entry

#### Scenario: Runner exits non-zero on case failure
- **WHEN** any executed case returns `status: "failed"`
- **THEN** the runner SHALL exit with code 1

#### Scenario: Runner exits zero when all cases pass or skip
- **WHEN** all executed cases have `status` in `{succeeded, unverified, skipped}`
- **THEN** the runner SHALL exit with code 0

#### Scenario: LLM_BASE_URL is forwarded to LLMClient, not hardcoded
- **WHEN** `LLM_BASE_URL=http://custom:9999` is set in env
- **THEN** the `LLMClient` constructed by the runner SHALL use `base_url="http://custom:9999"`

### Requirement: Validator vocabulary
The eval runner SHALL support a minimal validator vocabulary evaluated against the loop's `result` dict. For this ticket, only two validator forms are required:

- `<key>.nonempty` — passes if `result.get(key)` is a non-empty string (after stripping whitespace). Fails if the key is absent, `None`, not a string, or the string is empty after stripping.
- `<key>.len_gte: <N>` — passes if `result.get(key)` is a list (or other sequence) with `len(...) >= N`. Fails if the key is absent, `None`, not a sequence, or the sequence has fewer than N elements.

Each validator in `expect.validators` is evaluated and its result recorded in the `validators` list in the results JSON as `{ "name": "<expr>", "ok": <bool> }`.

#### Scenario: title.nonempty passes when result has non-empty title
- **WHEN** a case has validator `title.nonempty` and the loop returns `result={"title": "Some Title"}`
- **THEN** the validator entry SHALL be `{ "name": "title.nonempty", "ok": true }`

#### Scenario: title.nonempty fails when title is missing
- **WHEN** a case has validator `title.nonempty` and the loop returns `result={"other": "x"}`
- **THEN** the validator entry SHALL be `{ "name": "title.nonempty", "ok": false }`

#### Scenario: title.nonempty fails when title is empty string
- **WHEN** a case has validator `title.nonempty` and the loop returns `result={"title": ""}`
- **THEN** the validator entry SHALL be `{ "name": "title.nonempty", "ok": false }`

#### Scenario: items.len_gte: 1 passes when result has non-empty list
- **WHEN** a case has validator `items.len_gte: 1` and the loop returns `result={"items": ["a"]}`
- **THEN** the validator entry SHALL be `{ "name": "items.len_gte: 1", "ok": true }`

#### Scenario: items.len_gte: 1 fails when result has empty list
- **WHEN** a case has validator `items.len_gte: 1` and the loop returns `result={"items": []}`
- **THEN** the validator entry SHALL be `{ "name": "items.len_gte: 1", "ok": false }`

#### Scenario: items.len_gte: 1 fails when key is absent
- **WHEN** a case has validator `items.len_gte: 1` and the loop returns `result={}`
- **THEN** the validator entry SHALL be `{ "name": "items.len_gte: 1", "ok": false }`

### Requirement: Toy 2-case fixture suite
The repository SHALL include exactly two YAML case files in `task2/eval/cases/` for the base runner ticket:

1. `fixture-heading.yaml` — a fixture-backed case (`fixture: true`) that uses a local HTML fixture page. Task: read the page heading and return it. Expect schema: `{ title: str }`. Validators: `[title.nonempty]`. Budget: `{ steps: 5, usd: 0.05, seconds: 30 }`.
2. `fixture-count.yaml` — a fixture-backed case (`fixture: true`) that uses a local HTML fixture page with a list of items. Task: count or collect the list items and return them. Expect schema: `{ items: list[str] }`. Validators: `[items.len_gte: 1]`. Budget: `{ steps: 5, usd: 0.05, seconds: 30 }`.

Both cases SHALL refer to local fixture HTML pages already present in `task2/tests/fixtures/` (or a new fixture added under that directory) so they run without live network access.

#### Scenario: fixture-heading.yaml exists and is valid
- **WHEN** `task2/eval/cases/fixture-heading.yaml` is loaded
- **THEN** it SHALL parse as a valid case with `fixture: true`, `expect.validators: [title.nonempty]`

#### Scenario: fixture-count.yaml exists and is valid
- **WHEN** `task2/eval/cases/fixture-count.yaml` is loaded
- **THEN** it SHALL parse as a valid case with `fixture: true`, `expect.validators: [items.len_gte: 1]`
