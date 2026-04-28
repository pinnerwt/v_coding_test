## ADDED Requirements

### Requirement: benchmark --repeats N CLI flag

`scripts/benchmark.py`, invoked as `uv run python -m scripts.benchmark`, SHALL accept a new optional argument `--repeats N` (type `int`, default `1`). When `N == 1` the behavior SHALL be identical to the current single-run behavior. When `N > 1` each case is executed N times sequentially and the results are aggregated into a single `AggregatedCaseResult` per case before being written to the output JSON.

The CI workflow SHALL document that it passes `--repeats 3` for canary and drift suites; the default of `1` is preserved for all other callers.

#### Scenario: --repeats 1 is the default and preserves existing behavior

- **WHEN** `scripts.benchmark.main([])` is called without `--repeats`
- **THEN** each case is executed exactly once
- **AND** the results JSON shape is identical to the pre-feature shape

#### Scenario: --repeats 3 causes each case to run three times

- **GIVEN** a suite with one fixture case and `_run_case` patched to return a deterministic `CaseResult`
- **WHEN** `scripts.benchmark.main(["--repeats", "3"])` is called
- **THEN** `_run_case` is called exactly 3 times for that case
- **AND** the results JSON contains exactly one aggregated entry for the case

#### Scenario: --repeats value is validated as a positive integer

- **WHEN** `scripts.benchmark.main(["--repeats", "0"])` is called
- **THEN** the process SHALL exit with a non-zero code and print an error message

### Requirement: AggregatedCaseResult dataclass

`scripts/benchmark.py` SHALL define a frozen dataclass `AggregatedCaseResult` that holds the per-case aggregated statistics produced when `--repeats N` with `N > 1`. The dataclass SHALL be defined at module level.

A module-level type alias `RepeatStatus` SHALL be defined as:

```python
RepeatStatus = Literal["all_pass", "partial", "all_fail", "skipped"]
_VALID_REPEAT_STATUSES: frozenset[str] = frozenset(get_args(RepeatStatus))
```

`AggregatedCaseResult` SHALL include at minimum the following fields:

- `id: str` — case identifier.
- `repeat_status: RepeatStatus` — closed-set field. `__post_init__` SHALL raise `ValueError` if the value is not in `_VALID_REPEAT_STATUSES`.
- `repeats: int` — total number of runs attempted.
- `passed_runs: int` — number of runs whose `status` was in `_PASS_STATUSES`.
- `median_latency_ms: int` — median of `latency_ms_total` values across all N runs (0 for skipped).
- `p95_latency_ms: int` — 95th-percentile of `latency_ms_total` values across all N runs (0 for skipped).
- `stddev_usd: float` — population standard deviation of `usd` values across all N runs (0.0 for skipped or N == 1).
- `avg_mechanism_firings: float` — mean of total mechanism firing counts (`len(escalations) + replans`) across all N runs.
- `status: str` — derived: `"succeeded"` when `repeat_status == "all_pass"`, `"failed"` when `repeat_status in {"partial", "all_fail"}`, `"skipped"` when `repeat_status == "skipped"`.
- `steps: int` — median steps across all N runs (integer).
- `usd: float` — mean USD across all N runs.
- `prompt_tokens: int` — sum of `prompt_tokens` across all N runs.
- `completion_tokens: int` — sum of `completion_tokens` across all N runs.
- `latency_ms_total: int` — sum of `latency_ms_total` values across all N runs.
- `escalations: list[dict]` — escalations from the first (or last) representative run.
- `replans: int` — mean replans (rounded to nearest int).
- `cache_events: dict` — cache events from the representative run.
- `failure_class: str | None` — failure class from the most recent failing run, or `None` if all passed.
- `skip_reason: str | None` — skip reason if `repeat_status == "skipped"`, else `None`.

Statistics SHALL be computed using Python's stdlib `statistics` module (`statistics.median`, `statistics.pstdev`). No external dependency SHALL be added.

#### Scenario: AggregatedCaseResult construction with valid repeat_status

- **WHEN** `AggregatedCaseResult` is constructed with `repeat_status="all_pass"` and valid fields
- **THEN** construction SHALL succeed

#### Scenario: AggregatedCaseResult rejects unknown repeat_status

- **WHEN** `AggregatedCaseResult` is constructed with `repeat_status="unknown"`
- **THEN** `ValueError` SHALL be raised at construction time

#### Scenario: AggregatedCaseResult sets status to succeeded for all_pass

- **WHEN** `AggregatedCaseResult` is constructed with `repeat_status="all_pass"`
- **THEN** `result.status` SHALL equal `"succeeded"`

#### Scenario: AggregatedCaseResult sets status to failed for partial

- **WHEN** `AggregatedCaseResult` is constructed with `repeat_status="partial"`
- **THEN** `result.status` SHALL equal `"failed"`

### Requirement: Per-case repeat aggregation loop

`scripts/benchmark.py` SHALL define a function `aggregate_repeats(case, *, repeats, llm_client, browser) -> AggregatedCaseResult` that:

1. Runs `_run_case(case, llm_client, browser)` exactly `repeats` times sequentially.
2. Collects all N `CaseResult` instances.
3. Computes the aggregated statistics fields as defined in the `AggregatedCaseResult` requirement.
4. Determines `repeat_status` as:
   - `"skipped"` if all runs have `status == "skipped"`.
   - `"all_pass"` if all runs have `status` in `_PASS_STATUSES`.
   - `"all_fail"` if no run has `status` in `_PASS_STATUSES` (and not all skipped).
   - `"partial"` otherwise (some pass, some fail).
5. Returns an `AggregatedCaseResult`.

When `repeats == 1`, `benchmark.py` SHALL NOT call `aggregate_repeats`; it SHALL call `_run_case` directly and use the `CaseResult` as-is (preserving existing behavior).

#### Scenario: All 3 runs pass → all_pass with 3/3

- **GIVEN** `_run_case` is patched to always return `CaseResult(status="succeeded", ...)`
- **WHEN** `aggregate_repeats(case, repeats=3, ...)` is called
- **THEN** the returned `AggregatedCaseResult.repeat_status` SHALL equal `"all_pass"`
- **AND** `passed_runs` SHALL equal `3`
- **AND** `repeats` SHALL equal `3`

#### Scenario: 1 of 3 runs passes → partial with 1/3

- **GIVEN** `_run_case` is patched with a flaky stub that returns `"succeeded"` on the first call and `"failed"` on subsequent calls
- **WHEN** `aggregate_repeats(case, repeats=3, ...)` is called
- **THEN** the returned `AggregatedCaseResult.repeat_status` SHALL equal `"partial"`
- **AND** `passed_runs` SHALL equal `1`

#### Scenario: All 3 runs fail → all_fail with 0/3

- **GIVEN** `_run_case` is patched to always return `CaseResult(status="failed", ...)`
- **WHEN** `aggregate_repeats(case, repeats=3, ...)` is called
- **THEN** the returned `AggregatedCaseResult.repeat_status` SHALL equal `"all_fail"`
- **AND** `passed_runs` SHALL equal `0`

#### Scenario: median_latency_ms is the median of N latency values

- **GIVEN** `_run_case` returns latency values `[100, 200, 300]` across 3 runs
- **WHEN** `aggregate_repeats(case, repeats=3, ...)` is called
- **THEN** `median_latency_ms` SHALL equal `200`

#### Scenario: stddev_usd is 0.0 for N == 1 run

- **GIVEN** `_run_case` returns one result with `usd=0.5`
- **WHEN** `aggregate_repeats(case, repeats=1, ...)` is called
- **THEN** `stddev_usd` SHALL equal `0.0`

### Requirement: Updated results.json schema for aggregated runs

When `benchmark.py` is invoked with `--repeats N` and `N > 1`, each case entry in the written `results.json` SHALL include all standard `CaseResult` fields PLUS the following aggregation fields:

```json
{
  "id": "<case-id>",
  "repeats": <N>,
  "passed_runs": <int>,
  "repeat_status": "<all_pass|partial|all_fail|skipped>",
  "median_latency_ms": <int>,
  "p95_latency_ms": <int>,
  "stddev_usd": <float>,
  "avg_mechanism_firings": <float>,
  ...existing CaseResult fields...
}
```

When `--repeats 1` (the default), the results JSON SHALL NOT include the aggregation fields and SHALL be identical in shape to the pre-feature format.

#### Scenario: results.json with --repeats 3 contains aggregation fields

- **GIVEN** `benchmark.main(["--repeats", "3"])` is called with `_run_case` and `Browser`/`LLMClient` patched
- **WHEN** the results JSON is read back
- **THEN** each case entry SHALL have keys `repeats`, `passed_runs`, `repeat_status`, `median_latency_ms`, `p95_latency_ms`, `stddev_usd`, `avg_mechanism_firings`

#### Scenario: results.json with --repeats 1 (default) has no aggregation fields

- **GIVEN** `benchmark.main([])` is called with patched clients
- **WHEN** the results JSON is read back
- **THEN** case entries SHALL NOT have a `repeats` key
- **AND** SHALL NOT have a `repeat_status` key

### Requirement: TDD test shapes for bench repeats

The test file `task2/tests/test_bench_repeats.py` SHALL contain at minimum the following two test shapes.

**Test 1 — Deterministic mock, 3/3 pass rate:**
A test that calls `aggregate_repeats` (or `benchmark.main` end-to-end) with `--repeats 3` and a deterministic `_run_case` stub that always returns a passing `CaseResult`. The test asserts `passed_runs == 3`, `repeats == 3`, and `repeat_status == "all_pass"`.

**Test 2 — Flaky stub, fractional pass rate:**
A test that calls `aggregate_repeats` with `--repeats 3` and a stub whose `status` alternates (e.g. `["succeeded", "failed", "failed"]`). The test asserts `passed_runs == 1`, `repeats == 3`, and `repeat_status == "partial"`.

Both tests SHALL use `unittest.mock.patch` to stub `_run_case` — the real LLM client and browser SHALL NOT be called.

#### Scenario: Deterministic stub produces 3/3 result

- **GIVEN** `_run_case` is patched at `scripts.benchmark._run_case` to always return a `CaseResult` with `status="succeeded"`, `latency_ms_total=100`, `usd=0.01`, `escalations=[]`, `replans=0`
- **WHEN** `aggregate_repeats(case, repeats=3, llm_client=ANY, browser=ANY)` is called
- **THEN** the result SHALL have `passed_runs == 3`, `repeats == 3`, `repeat_status == "all_pass"`

#### Scenario: Flaky stub produces fractional result

- **GIVEN** `_run_case` is patched to return statuses `["succeeded", "failed", "failed"]` in order
- **WHEN** `aggregate_repeats(case, repeats=3, llm_client=ANY, browser=ANY)` is called
- **THEN** the result SHALL have `passed_runs == 1`, `repeats == 3`, `repeat_status == "partial"`
