# eval-metrics Specification

## Purpose
TBD - created by archiving change implement-quantitative-eval. Update Purpose after archive.

## Requirements

### Requirement: CaseResult carries quantitative fields

`scripts.eval.CaseResult` SHALL gain the following fields (with zero/empty defaults for backward compatibility):

- `prompt_tokens: int = 0`
- `completion_tokens: int = 0`
- `latency_ms_total: int = 0`
- `latency_ms_per_step: list[int] = field(default_factory=list)`
- `step_breakdown: list[dict] = field(default_factory=list)`

Existing fields (`id`, `status`, `steps`, `usd`, `l_tier_counts`, `validators`) are unchanged.

#### Scenario: CaseResult is constructible with only legacy fields

- **WHEN** `CaseResult(id="x", status="succeeded", steps=0, usd=0.0, l_tier_counts={}, validators=[])` is constructed
- **THEN** `prompt_tokens` SHALL equal `0`, `latency_ms_per_step` SHALL equal `[]`

### Requirement: _run_case threads loop metrics into CaseResult

`_run_case` SHALL populate `CaseResult` from the `RunResult` returned by `loop()`:

- `steps` ← `run_result.steps`
- `usd` ← `run_result.usd`
- `prompt_tokens` ← `run_result.prompt_tokens`
- `completion_tokens` ← `run_result.completion_tokens`
- `latency_ms_total` ← `run_result.latency_ms_total`
- `latency_ms_per_step` ← `run_result.latency_ms_per_step`
- `step_breakdown` ← `run_result.step_breakdown`
- `l_tier_counts` ← empty dict (populated later when locate events are threaded; out of scope for this ticket)

#### Scenario: _run_case produces non-zero steps and usd when loop returns metrics

- **GIVEN** a mocked `loop()` that returns `RunResult(status="succeeded", result={}, evidence={"url":"u","text_snippet":"t"}, steps=3, prompt_tokens=400, completion_tokens=60, usd=0.0009, latency_ms_total=1200, latency_ms_per_step=[400,400,400], step_breakdown=[...])`
- **WHEN** `_run_case(case, llm_client, browser)` is called with a case whose loop is replaced by the mock
- **THEN** the returned `CaseResult.steps` SHALL equal `3`
- **AND** `CaseResult.usd` SHALL equal `0.0009`
- **AND** `CaseResult.prompt_tokens` SHALL equal `400`
- **AND** `CaseResult.latency_ms_total` SHALL equal `1200`

### Requirement: Results JSON schema includes quantitative fields

The JSON written to `eval/results/<ts>.json` SHALL include the new `CaseResult` fields in each case object. The `cases` array entries SHALL have the shape:

```json
{
  "id": "...",
  "status": "...",
  "steps": <int>,
  "usd": <float>,
  "prompt_tokens": <int>,
  "completion_tokens": <int>,
  "latency_ms_total": <int>,
  "latency_ms_per_step": [<int>, ...],
  "step_breakdown": [{"step": <int>, "latency_ms": <int>, "prompt_tokens": <int>, "completion_tokens": <int>, "usd": <float>, "tool_calls": [<str>]}, ...],
  "l_tier_counts": {},
  "validators": [...]
}
```

#### Scenario: Results JSON is serialisable and contains new fields

- **GIVEN** a `CaseResult` with `prompt_tokens=100`, `latency_ms_per_step=[200, 300]`, `step_breakdown=[...]`
- **WHEN** `asdict(case_result)` is passed through `json.dumps`
- **THEN** the resulting JSON SHALL have `"prompt_tokens": 100` and `"latency_ms_per_step": [200, 300]`
