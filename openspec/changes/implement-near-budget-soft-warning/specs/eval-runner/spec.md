## MODIFIED Requirements

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
          "tool_calls": ["<name>", ...]
        }
      ],
      "near_budget": <bool>,
      "...": "..."
    }
  ]
}
```

Each per-case entry SHALL include a `near_budget: bool` field. `near_budget` SHALL be `True` when the case `status` is in `{succeeded, unverified}` AND any of the following ratios is `≥ 0.80`:

- `steps / budget.steps`
- `usd / budget.usd`
- `latency_ms_total / 1000 / budget.seconds`

`near_budget` SHALL be `False` for any case whose `status` is not in `{succeeded, unverified}` (i.e. failed, blocked, timeout, skipped) regardless of how close its observed metrics came to the budget. When the case's `budget` dict omits a given axis, that axis SHALL be ignored in the ratio computation; only present axes are considered.

#### Scenario: near_budget is True at 80% of step budget on a passing case

- **GIVEN** a case with `budget = {"steps": 5, "usd": 1.0, "seconds": 30}`
- **AND** a `RunResult(status="succeeded", steps=4, usd=0.0, latency_ms_total=0)` returned by the loop
- **WHEN** `_run_case` builds the `CaseResult`
- **THEN** the returned `CaseResult.near_budget` SHALL be `True`

#### Scenario: near_budget is False just below threshold on a passing case

- **GIVEN** a case with `budget = {"steps": 5, "usd": 1.0, "seconds": 30}`
- **AND** a `RunResult(status="succeeded", steps=3, usd=0.0, latency_ms_total=0)` returned by the loop
- **WHEN** `_run_case` builds the `CaseResult`
- **THEN** the returned `CaseResult.near_budget` SHALL be `False`

#### Scenario: near_budget is False for a failed/timeout case at the cap

- **GIVEN** a case with `budget = {"steps": 5, "usd": 1.0, "seconds": 30}`
- **AND** a `RunResult(status="timeout", steps=5, usd=0.0, latency_ms_total=0)` returned by the loop
- **WHEN** `_run_case` builds the `CaseResult`
- **THEN** the returned `CaseResult.near_budget` SHALL be `False`

#### Scenario: near_budget trips on the usd axis

- **GIVEN** a case with `budget = {"steps": 5, "usd": 0.05, "seconds": 30}`
- **AND** a `RunResult(status="succeeded", steps=1, usd=0.04, latency_ms_total=0)` returned by the loop
- **WHEN** `_run_case` builds the `CaseResult`
- **THEN** the returned `CaseResult.near_budget` SHALL be `True`

#### Scenario: near_budget trips on the seconds axis

- **GIVEN** a case with `budget = {"steps": 5, "usd": 1.0, "seconds": 30}`
- **AND** a `RunResult(status="succeeded", steps=1, usd=0.0, latency_ms_total=24_000)` returned by the loop
- **WHEN** `_run_case` builds the `CaseResult`
- **THEN** the returned `CaseResult.near_budget` SHALL be `True`

#### Scenario: near_budget ignores axes absent from the budget dict

- **GIVEN** a case with `budget = {"steps": 5}` (no `usd` or `seconds` keys)
- **AND** a `RunResult(status="succeeded", steps=4, usd=999.0, latency_ms_total=999_999)` returned by the loop
- **WHEN** `_run_case` builds the `CaseResult`
- **THEN** the returned `CaseResult.near_budget` SHALL be `True` (tripped by the present `steps` axis)
- **AND** the absent `usd` and `seconds` axes SHALL not raise or contribute to the decision
