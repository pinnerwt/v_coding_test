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
          "tool_calls": [<str>]
        }
      ],
      "l_tier_counts": { "<tier>": <int>, ... },
      "validators": [{ "name": "<expr>", "ok": <bool> }, ...]
    }
  ]
}
```

All new fields (`prompt_tokens`, `completion_tokens`, `latency_ms_total`, `latency_ms_per_step`, `step_breakdown`) SHALL default to zero / empty when a case is skipped or the loop returns zero-metric results.

#### Scenario: Results JSON is valid and contains new fields after a real run

- **GIVEN** a suite run with at least one fixture case that completes via a mocked loop returning non-zero metrics
- **WHEN** the results JSON is read back from disk
- **THEN** the case entry SHALL have `"prompt_tokens"` and `"latency_ms_per_step"` keys
- **AND** their values SHALL be non-zero

#### Scenario: Skipped case has zero-valued metric fields

- **GIVEN** a case that is skipped (not fixture, not live)
- **WHEN** the results JSON is read back
- **THEN** the case entry SHALL have `"steps": 0`, `"usd": 0.0`, `"prompt_tokens": 0`, `"latency_ms_per_step": []`
