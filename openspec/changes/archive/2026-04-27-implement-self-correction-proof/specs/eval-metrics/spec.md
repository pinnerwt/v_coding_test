## MODIFIED Requirements

### Requirement: CaseResult carries quantitative fields

`scripts.eval.CaseResult` SHALL gain the following fields (with zero/empty defaults for backward compatibility):

- `prompt_tokens: int = 0`
- `completion_tokens: int = 0`
- `latency_ms_total: int = 0`
- `latency_ms_per_step: list[int] = field(default_factory=list)`
- `step_breakdown: list[dict] = field(default_factory=list)`
- `escalations: list[dict] = field(default_factory=list)` — one entry per escalation event in the trace; each entry has keys `intent`, `from_tier`, `to_tier`, `reason`.
- `replans: int = 0` — count of replan events in the trace.
- `cache_events: dict = field(default_factory=dict)` — aggregate cache hit/invalidation/miss counts; keys `hits`, `invalidations`, `misses` (all int, all default 0).

Existing fields (`id`, `status`, `steps`, `usd`, `l_tier_counts`, `validators`) are unchanged.

#### Scenario: CaseResult is constructible with only legacy fields

- **WHEN** `CaseResult(id="x", status="succeeded", steps=0, usd=0.0, l_tier_counts={}, validators=[])` is constructed
- **THEN** `prompt_tokens` SHALL equal `0`, `latency_ms_per_step` SHALL equal `[]`
- **AND** `escalations` SHALL equal `[]`, `replans` SHALL equal `0`, `cache_events` SHALL equal `{}`

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
- `escalations`, `replans`, `cache_events` ← from `_aggregate_diagnostics(writer, run_id)` called after `loop()` returns

`_run_case` SHALL construct an in-memory `TraceWriter` and a `uuid4()` run_id, pass both to `loop()`, and call `_aggregate_diagnostics` after `loop()` returns.

#### Scenario: _run_case produces non-zero steps and usd when loop returns metrics

- **GIVEN** a mocked `loop()` that returns `RunResult(status="succeeded", result={}, evidence={"url":"u","text_snippet":"t"}, steps=3, prompt_tokens=400, completion_tokens=60, usd=0.0009, latency_ms_total=1200, latency_ms_per_step=[400,400,400], step_breakdown=[...])`
- **WHEN** `_run_case(case, llm_client, browser)` is called with a case whose loop is replaced by the mock
- **THEN** the returned `CaseResult.steps` SHALL equal `3`
- **AND** `CaseResult.usd` SHALL equal `0.0009`
- **AND** `CaseResult.prompt_tokens` SHALL equal `400`
- **AND** `CaseResult.latency_ms_total` SHALL equal `1200`

### Requirement: Results JSON schema includes quantitative and diagnostic fields

The JSON written to `eval/results/<ts>.json` SHALL include all `CaseResult` fields in each case object, including the new diagnostic fields. The `cases` array entries SHALL have the shape:

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
  "step_breakdown": [...],
  "l_tier_counts": {},
  "validators": [...],
  "escalations": [{"intent": "...", "from_tier": "...", "to_tier": "...", "reason": "..."}, ...],
  "replans": <int>,
  "cache_events": {"hits": <int>, "invalidations": <int>, "misses": <int>}
}
```

#### Scenario: Results JSON is serialisable and contains new fields

- **GIVEN** a `CaseResult` with `prompt_tokens=100`, `latency_ms_per_step=[200, 300]`, `escalations=[...]`, `replans=1`, `cache_events={"hits": 0, "invalidations": 1, "misses": 0}`
- **WHEN** `asdict(case_result)` is passed through `json.dumps`
- **THEN** the resulting JSON SHALL have `"prompt_tokens": 100`, `"latency_ms_per_step": [200, 300]`
- **AND** SHALL have `"replans": 1` and `"escalations"` key
