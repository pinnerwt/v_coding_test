## MODIFIED Requirements

### Requirement: score.py reads a results JSON and emits a markdown scoreboard

The latency percentile section of the scoreboard SHALL change the input to the `_percentile` function for p50/p95 computation:

- **WHEN** computing latency percentiles over non-skipped cases, `generate_scoreboard` SHALL use `c.get("median_latency_ms", c.get("latency_ms_total", 0))` for each case, preferring `median_latency_ms` when present and falling back to `latency_ms_total` for backward compatibility with old results files and `--repeats 1` runs (where both fields are absent/identical in meaning).
- The fallback ensures that results JSON files without a `median_latency_ms` key continue to produce a valid scoreboard without raising exceptions.

**All other sections of this requirement are unchanged.**

#### Scenario: Latency percentiles use median_latency_ms when present

- **GIVEN** a results file with three non-skipped cases having `median_latency_ms` values `[100, 200, 800]` and `latency_ms_total` values `[300, 600, 2400]`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the output SHALL contain `p50: 200ms`
- **AND** the output SHALL contain `p95: 800ms`

#### Scenario: Latency percentiles fall back to latency_ms_total when median_latency_ms is absent

- **GIVEN** a results file with three non-skipped cases having `latency_ms_total` values `[100, 200, 800]` and no `median_latency_ms` key
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the output SHALL contain `p50: 200ms`
- **AND** the output SHALL contain `p95: 800ms`
- **AND** no exception SHALL be raised
