# eval-runner Specification

## Purpose
TBD - created by archiving change implement-eval-runner. Update Purpose after archive.
## Requirements
### Requirement: Case YAML schema
Each eval case SHALL be expressed as a YAML file under `task2/eval/cases/` with the following fields:

- `id: str` — unique kebab-case identifier for the case (used as the key in results JSON).
- `domain: str` — the target domain or fixture identifier (e.g. `fixture`, `arxiv.org`).
- `category: str` — one of: `search-and-extract`, `form-filling`, `multi-page-navigation`, `conditional-pick`, `read-and-summarize`, `drift`, `correction`.
- `task: str` — the natural-language task string passed verbatim to the agent loop.
- `expect.schema: dict` — the expected output key types (e.g. `{ title: str, authors: list[str] }`). Stored and forwarded to the loop; full JSONSchema validation is deferred.
- `expect.validators: list[str]` — list of validator expressions evaluated against the loop's `result` dict. Supported vocabulary for this ticket: `<key>.nonempty` and `<key>.len_gte: <N>`.
- `budget.steps: int` — maximum agent loop steps for this case.
- `budget.usd: float` — maximum USD spend for this case.
- `budget.seconds: int` — wall-clock timeout in seconds.
- `fixture: bool` (optional, default `false`) — when `true`, the case is CI-safe and runs without `--live`.
- `variants: list[str]` (optional) — when present, the runner expands this case into one sub-run per variant. Each variant value is a short identifier (e.g. `"v1"`, `"v2"`) appended to the case `id` with a hyphen to form the sub-run id. If absent or empty, the case runs as a single run with its original `id`.
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

#### Scenario: variants field parsed as list of strings
- **WHEN** `task2/eval/cases/drift-submit-form.yaml` is loaded
- **THEN** the returned dict SHALL have `variants == ["v1", "v2"]`

#### Scenario: shared_cache field is optional and backward-compatible

- **WHEN** a YAML case file does not contain a `shared_cache` key
- **THEN** `load_cases` SHALL succeed and the case SHALL run with `shared_cache` defaulting to `false`

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
      "prompt_tokens": <int>,
      "completion_tokens": <int>,
      "latency_ms_total": <int>,
      "latency_ms_per_step": [<int>, ...],
      "step_breakdown": [
        {
          "step": <int>,
          "latency_ms": <int>,
          "prompt_tokens": <int>,
          "completion_tokens": <int>,
          "usd": <float>,
          "tool_calls": [<str>]
        }
      ],
      "l_tier_counts": { "<tier>": <int>, ... },
      "validators": [{ "name": "<expr>", "ok": <bool> }, ...]
    }
  ]
}
```

- `run_at`: ISO 8601 UTC timestamp of when the suite run started.
- `cases`: ordered list of per-case results, one entry per case regardless of skip status. For variantized cases, the entry `id` is the expanded sub-run id (e.g. `drift-submit-form-v1`), not the parent case id.
- `status`: one of `succeeded`, `unverified`, `failed`, `blocked`, `timeout`, `skipped`. `skipped` is used when a non-fixture case is excluded because `--live` was not passed.
- `steps`: number of agent loop steps consumed (integer ≥ 0; 0 for skipped cases).
- `usd`: estimated USD cost of the case run (float ≥ 0.0; 0.0 for skipped cases or when cost tracking is not yet wired).
- `l_tier_counts`: dict mapping L-tier name (e.g. `"L1_ax"`, `"L2_dom"`, `"L3_rerank"`, `"L4_vision"`, `"cache"`) to the integer number of locate attempts that resolved at that tier for this case. Empty dict `{}` is valid (e.g. for skipped cases or cases with no locate calls).
- `validators`: list of validator results, one per entry in `expect.validators`. Empty list `[]` is valid when `expect.validators` is empty or the case was skipped.

All new fields (`prompt_tokens`, `completion_tokens`, `latency_ms_total`, `latency_ms_per_step`, `step_breakdown`) SHALL default to zero / empty when a case is skipped or the loop returns zero-metric results.

#### Scenario: Results JSON exists after runner completes
- **WHEN** `scripts/eval.py` is invoked and all cases complete (or are skipped)
- **THEN** a JSON file SHALL exist at `eval/results/<ts>.json` relative to `task2/`

#### Scenario: Results JSON contains one entry per case
- **WHEN** the suite has 2 cases and `--live` is absent and both have `fixture: true`
- **THEN** the `cases` array in the results JSON SHALL have exactly 2 entries

#### Scenario: Skipped case has status skipped and zero steps
- **WHEN** a case has no `fixture: true` and `--live` is absent
- **THEN** the case entry in results JSON SHALL have `status: "skipped"`, `steps: 0`, `usd: 0.0`, `l_tier_counts: {}`, `validators: []`

#### Scenario: Skipped case has zero-valued metric fields

- **GIVEN** a case that is skipped (not fixture, not live)
- **WHEN** the results JSON is read back
- **THEN** the case entry SHALL have `"steps": 0`, `"usd": 0.0`, `"prompt_tokens": 0`, `"latency_ms_per_step": []`

#### Scenario: Results JSON is valid JSON
- **WHEN** the results file is written
- **THEN** `json.loads(results_file.read_text())` SHALL succeed without error

#### Scenario: l_tier_counts is always a dict
- **WHEN** a case completes with no locate calls (e.g. the task calls `done` immediately)
- **THEN** `l_tier_counts` SHALL be `{}` (empty dict), NOT `null` or absent

#### Scenario: Results JSON is valid and contains new fields after a real run

- **GIVEN** a suite run with at least one fixture case that completes via a mocked loop returning non-zero metrics
- **WHEN** the results JSON is read back from disk
- **THEN** the case entry SHALL have `"prompt_tokens"` and `"latency_ms_per_step"` keys
- **AND** their values SHALL be non-zero

### Requirement: Eval runner CLI
The system SHALL expose `scripts/eval.py` as a runnable script from `task2/` via `uv run python scripts/eval.py`. The CLI SHALL accept the following optional flags:

- `--live`: include non-fixture (live) cases in the run. Without this flag, only cases with `fixture: true` are executed.
- `--case <id>`: run only the case with the given `id`. Can be combined with `--live`.

The runner SHALL print per-case progress to stdout as each case completes (format: `[PASS|FAIL|SKIP] <id> (<steps> steps, $<usd>)`). After the suite completes, it SHALL print the path to the written results JSON.

The runner SHALL exit with code 0 if all executed cases have `status` in `{succeeded, unverified, skipped}`. It SHALL exit with code 1 if any executed case has `status` in `{failed, blocked, timeout}`.

The runner SHALL NOT hardcode any LLM provider URL. `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY` are read from env. When `LLM_MODEL` is unset, `build_clients()` SHALL fall back to `agent.llm._DEFAULT_LLM_MODEL` — NOT to a locally-defined string literal. `LLM_BASE_URL` defaults to `http://localhost:8090/v1`; `LLM_API_KEY` defaults to `"local"`.

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

#### Scenario: build_clients uses shared default when LLM_MODEL is unset
- **GIVEN** `LLM_MODEL` is not set in the process environment
- **WHEN** `build_clients()` is invoked
- **THEN** the `LLMClient` SHALL be constructed with `model` equal to `agent.llm._DEFAULT_LLM_MODEL` (`"qwen3-5-27b"`)
- **AND** the string `"qwen3"` SHALL NOT appear as a default fallback anywhere in `scripts/eval.py`

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
The repository SHALL include exactly two YAML case files in `task2/eval/cases/` for this ticket:

1. `fixture-heading.yaml` — a fixture-backed case (`fixture: true`) that uses a local HTML fixture page. Task: read the page heading and return it. Expect schema: `{ title: str }`. Validators: `[title.nonempty]`. Budget: `{ steps: 5, usd: 0.05, seconds: 30 }`.
2. `fixture-count.yaml` — a fixture-backed case (`fixture: true`) that uses a local HTML fixture page with a list of items. Task: count or collect the list items and return them. Expect schema: `{ items: list[str] }`. Validators: `[items.len_gte: 1]`. Budget: `{ steps: 5, usd: 0.05, seconds: 30 }`.

Both cases SHALL refer to local fixture HTML pages already present in `task2/tests/fixtures/` (or a new fixture added under that directory) so they run without live network access.

#### Scenario: fixture-heading.yaml exists and is valid
- **WHEN** `task2/eval/cases/fixture-heading.yaml` is loaded
- **THEN** it SHALL parse as a valid case with `fixture: true`, `expect.validators: [title.nonempty]`

#### Scenario: fixture-count.yaml exists and is valid
- **WHEN** `task2/eval/cases/fixture-count.yaml` is loaded
- **THEN** it SHALL parse as a valid case with `fixture: true`, `expect.validators: [items.len_gte: 1]`

### Requirement: Case YAML live field
The eval runner's case YAML schema SHALL recognize `live: true` as an optional informational field. Its presence SHALL NOT alter the runner's skip logic; skip logic remains driven solely by the absence of `fixture: true`. A case with `live: true` and no `fixture: true` SHALL be skipped when `run_suite` is called with `live=False`.

#### Scenario: Live-flagged case skipped without --live
- **WHEN** a YAML case has `live: true` and no `fixture: true`, and `run_suite` is called with `live=False`
- **THEN** the case produces a `CaseResult` with `status == "skipped"` without calling `_run_case`

#### Scenario: Live-flagged case executed with --live
- **WHEN** a YAML case has `live: true` and no `fixture: true`, and `run_suite` is called with `live=True`
- **THEN** `_run_case` is called for that case and its result (not `"skipped"`) appears in the results JSON

#### Scenario: load_cases accepts live field without error
- **WHEN** `load_cases` is called on a YAML file containing `live: true`
- **THEN** no `ValueError` is raised and the returned dict includes `live == True`

### Requirement: CaseResult skip_reason field
`CaseResult` SHALL include a `skip_reason` field typed as
`Literal["live_disabled", "infra_unavailable", "fixture_missing", "feature_not_implemented"] | None`
with a default value of `None`.

The field SHALL appear in the serialized results JSON as `"skip_reason"` on every case entry. For non-skipped cases it SHALL be `null`. For skipped cases it SHALL be one of the four valid literal values.

`__post_init__` SHALL enforce two invariants at construction time:

1. When `status == "skipped"`, `skip_reason` MUST be non-`None`. Constructing a `CaseResult` with `status="skipped"` and `skip_reason=None` SHALL raise `ValueError`.
2. When `skip_reason` is non-`None`, its value MUST be one of the four allowed literals. Passing an unrecognized string SHALL raise `ValueError`.

#### Scenario: skip_reason is None for non-skipped case
- **WHEN** a `CaseResult` is constructed with `status="succeeded"` and `skip_reason=None`
- **THEN** construction SHALL succeed and `result.skip_reason` SHALL be `None`

#### Scenario: skip_reason is required when status is skipped
- **WHEN** a `CaseResult` is constructed with `status="skipped"` and `skip_reason=None`
- **THEN** `ValueError` SHALL be raised at construction time

#### Scenario: unrecognized skip_reason is rejected at construction
- **WHEN** a `CaseResult` is constructed with `skip_reason="unknown_reason"`
- **THEN** `ValueError` SHALL be raised at construction time

#### Scenario: valid skip_reason values are accepted
- **WHEN** a `CaseResult` is constructed with `status="skipped"` and each of `"live_disabled"`, `"infra_unavailable"`, `"fixture_missing"`, `"feature_not_implemented"`
- **THEN** construction SHALL succeed for each value

### Requirement: live_disabled skip path sets skip_reason
When `run_suite()` skips a case because `live=False` and the case lacks `fixture: true`, the resulting `CaseResult` SHALL have `skip_reason="live_disabled"`.

#### Scenario: --no-live run produces live_disabled skip_reason for non-fixture case
- **GIVEN** a case with no `fixture: true` field
- **AND** `run_suite()` is called with `live=False`
- **WHEN** the results JSON is read back
- **THEN** the case entry SHALL have `"status": "skipped"` and `"skip_reason": "live_disabled"`

#### Scenario: fixture case does not get skip_reason when run without --live
- **GIVEN** a case with `fixture: true`
- **AND** `run_suite()` is called with `live=False`
- **WHEN** the case executes via `_run_case`
- **THEN** the resulting `CaseResult.skip_reason` SHALL be `None` (the case ran; it was not skipped)

### Requirement: fixture_missing skip path sets skip_reason
When a case references a `fixture_path` (a filesystem path to a local HTML fixture) and that path does not exist on disk, `run_suite()` SHALL produce a `CaseResult` with `status="skipped"` and `skip_reason="fixture_missing"` instead of raising an exception or calling `_run_case`.

The `fixture_path` key in the case YAML is optional. Its absence SHALL NOT change existing behaviour.

#### Scenario: missing fixture file produces fixture_missing skip
- **GIVEN** a case dict with `fixture_path` set to a path that does not exist on disk
- **AND** `run_suite()` is called with `live=False`
- **WHEN** the suite processes that case
- **THEN** the `CaseResult` SHALL have `status="skipped"` and `skip_reason="fixture_missing"`
- **AND** `_run_case` SHALL NOT be called for that case

#### Scenario: fixture_path absent leaves existing skip logic unchanged
- **GIVEN** a case dict with no `fixture_path` key
- **WHEN** `run_suite()` processes that case
- **THEN** skip/run behaviour SHALL be identical to before this change


### Requirement: Case YAML canary field

The eval runner's case YAML schema SHALL recognize an optional `canary: bool` field (default `false`). Its presence SHALL NOT alter the runner's skip logic, execution order, or result status computation. A case with `canary: true` runs exactly as a case without it; `canary` is informational metadata consumed downstream by `canary_gate.py`.

`load_cases` SHALL accept YAML files that include `canary: true` or `canary: false` without raising a `ValueError`. The field SHALL be forwarded verbatim in the returned case dict.

`CaseResult` SHALL gain a `canary: bool = False` field. `__post_init__` SHALL NOT add any new invariant on `canary`. The field SHALL appear in the serialized results JSON on every case entry (as `"canary": true` or `"canary": false`).

`run_suite` SHALL pass `canary=case.get("canary", False)` when constructing each `CaseResult` via `_skipped_result` or `_run_case`. `_run_case` itself does not need to inspect `canary`; it merely accepts and forwards it to `CaseResult`.

#### Scenario: load_cases accepts canary field without error

- **WHEN** `load_cases` is called on a YAML file containing `canary: true`
- **THEN** no `ValueError` is raised and the returned dict has `canary == True`

#### Scenario: load_cases sets canary to false by default when field is absent

- **WHEN** `load_cases` is called on a YAML file with no `canary` key
- **THEN** the returned dict has `canary` either absent or falsy (gate uses `.get("canary", False)`)

#### Scenario: CaseResult accepts canary=True without error

- **WHEN** `CaseResult` is constructed with `canary=True` and `status="succeeded"`
- **THEN** construction SHALL succeed and `result.canary` SHALL be `True`

#### Scenario: CaseResult canary defaults to False

- **WHEN** `CaseResult` is constructed without specifying `canary`
- **THEN** `result.canary` SHALL be `False`

#### Scenario: canary field appears in results JSON for canary-tagged case

- **GIVEN** a case with `canary: true` is run by `run_suite`
- **WHEN** the results JSON is parsed
- **THEN** the case entry SHALL have `"canary": true`

#### Scenario: canary field appears as false in results JSON for non-canary case

- **GIVEN** a case YAML with no `canary` key
- **WHEN** `run_suite` produces the results JSON
- **THEN** the case entry SHALL have `"canary": false`

### Requirement: iter_runnable_subcases shared helper

`eval.py` SHALL expose a module-level generator function with the exact signature:

- `iter_runnable_subcases(parent_cases: list[dict], *, live: bool) -> Iterator[tuple[dict, LocatorCache | None, SkipReason | None]]`

Each call to the generator iterates over `parent_cases` and, for each parent case, yields one tuple per runnable (or skippable) sub-case. The three elements of each yielded tuple are:

- `case: dict` — the fully-formed sub-case dict ready to pass to `_run_case`. When the parent has `variants`, the sub-case `id` is `<parent-id>-<variant>` and all other fields are inherited from the parent. When the parent has no `variants`, the sub-case dict is the parent dict unchanged.
- `shared_cache: LocatorCache | None` — the shared `LocatorCache(path=":memory:")` instance constructed once per parent case when `shared_cache: true` and `variants` is present; `None` otherwise. The same instance SHALL be yielded for every sub-case of the same parent when shared-cache is active (identity `is` check).
- `skip_reason: SkipReason | None` — one of `"fixture_missing"`, `"live_disabled"`, or `None`. `None` means the sub-case should be executed. Non-`None` means the consumer SHALL emit a skipped `CaseResult` and SHALL NOT call `_run_case`.

**Skip ladder (applied per sub-case in order):**

- If the sub-case has a `fixture_path` key whose value refers to a path that does not exist on disk, `skip_reason` is `"fixture_missing"`.
- Else if `live=False` and the sub-case does not have `fixture: true`, `skip_reason` is `"live_disabled"`.
- Else `skip_reason` is `None`.

The helper SHALL NOT call `_run_case`, construct a `CaseResult`, or perform any I/O beyond the filesystem existence check for `fixture_path`.

`run_suite` in `eval.py` and the `--repeats > 1` block in `benchmark.py::main` SHALL both consume `iter_runnable_subcases` and replace their inline variant-expansion and skip-ladder blocks with `for case, cache, skip_reason in iter_runnable_subcases(parent_cases, live=live): ...`.

#### Scenario: Two-variant shared-cache yields same LocatorCache instance for both sub-cases

- **GIVEN** a parent case with `variants: ["v1", "v2"]`, `fixture: true`, and `shared_cache: true`
- **WHEN** `iter_runnable_subcases([parent_case], live=False)` is exhausted
- **THEN** exactly two tuples SHALL be yielded
- **AND** the `shared_cache` element of both tuples SHALL be the same `LocatorCache` object (identity `is` check)
- **AND** the `skip_reason` element of both tuples SHALL be `None`
- **AND** the first tuple `case["id"]` SHALL equal `<parent-id>-v1`
- **AND** the second tuple `case["id"]` SHALL equal `<parent-id>-v2`

#### Scenario: Live-only case yields live_disabled skip_reason when called with live=False

- **GIVEN** a parent case with `live: true` (no `fixture: true`) and no `variants`
- **WHEN** `iter_runnable_subcases([parent_case], live=False)` is exhausted
- **THEN** exactly one tuple SHALL be yielded
- **AND** the `skip_reason` element SHALL equal `"live_disabled"`
- **AND** the `shared_cache` element SHALL be `None`

#### Scenario: Fixture-missing case yields fixture_missing skip_reason

- **GIVEN** a parent case with `fixture: true`, `fixture_path` set to a path that does not exist on disk, and no `variants`
- **WHEN** `iter_runnable_subcases([parent_case], live=False)` is exhausted
- **THEN** exactly one tuple SHALL be yielded
- **AND** the `skip_reason` element SHALL equal `"fixture_missing"`
- **AND** the `shared_cache` element SHALL be `None`

#### Scenario: Non-variantized fixture case yields single tuple with no skip and no cache

- **GIVEN** a parent case with `fixture: true`, no `variants`, and no `fixture_path`
- **WHEN** `iter_runnable_subcases([parent_case], live=False)` is exhausted
- **THEN** exactly one tuple SHALL be yielded
- **AND** the `skip_reason` element SHALL be `None`
- **AND** the `shared_cache` element SHALL be `None`
- **AND** the `case` element SHALL be the parent case dict unchanged

#### Scenario: Variants without shared_cache yields None cache for both sub-cases

- **GIVEN** a parent case with `variants: ["v1", "v2"]`, `fixture: true`, and no `shared_cache` key (or `shared_cache: false`)
- **WHEN** `iter_runnable_subcases([parent_case], live=False)` is exhausted
- **THEN** exactly two tuples SHALL be yielded
- **AND** the `shared_cache` element of both tuples SHALL be `None`
- **AND** the `skip_reason` element of both tuples SHALL be `None`

### Requirement: _run_case failure_detail for LLMError

When `_run_case`'s `except Exception as exc:` handler catches an exception that is an instance of `agent.llm.LLMError`, it SHALL produce a `failure_detail` string that includes both the HTTP status code and a truncated body snippet, rather than the opaque `repr(exc)` form.

The required format is:
`f"LLMError(kind={exc.kind!r}, status={exc.status}, body={(exc.body or '')[:512]!r})"`

For any other exception type, `failure_detail` SHALL remain `repr(exc)` (no behavior change for non-`LLMError` exceptions).

`failure_class` SHALL remain `"tool_error"` for all exceptions caught by this handler.

`steps` SHALL remain `0` in the exception path (the true step count inside `loop()` is not accessible to `_run_case` when `loop()` raises).

#### Scenario: LLMError 400 produces structured failure_detail

- **GIVEN** `agent.loop.loop` is mocked to raise `LLMError("http 400", kind="http", status=400, body='{"error":{"type":"exceed_context_size_error","n_prompt_tokens":34074}}')`
- **WHEN** `_run_case(case, llm_client=ANY, browser=ANY)` is called
- **THEN** the returned `CaseResult.failure_detail` SHALL contain the substring `"status=400"`
- **AND** the returned `CaseResult.failure_detail` SHALL contain a slice of the body string (e.g. `"exceed_context_size_error"`)
- **AND** `CaseResult.failure_class` SHALL equal `"tool_error"`

#### Scenario: non-LLMError exceptions are unaffected

- **GIVEN** `agent.loop.loop` is mocked to raise `RuntimeError("unexpected")`
- **WHEN** `_run_case(case, llm_client=ANY, browser=ANY)` is called
- **THEN** the returned `CaseResult.failure_detail` SHALL equal `repr(RuntimeError("unexpected"))` (i.e. `"RuntimeError('unexpected')"`)
- **AND** `CaseResult.failure_class` SHALL equal `"tool_error"`
