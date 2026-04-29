## MODIFIED Requirements

### Requirement: AggregatedCaseResult dataclass

The `usd` field definition SHALL change from mean to sum convention:

- `usd: float` — **sum** of `usd` values across all N runs (previously: mean). This aligns `usd` with the sum convention already used by `prompt_tokens`, `completion_tokens`, and `latency_ms_total`.

**All other fields and validation rules are unchanged.**

#### Scenario: AggregatedCaseResult.usd is the sum of per-run usd values

- **GIVEN** `aggregate_repeats` is called with `repeats=3` and `_run_case` returning `usd=0.01` on each of the three runs
- **WHEN** `aggregate_repeats` returns the `AggregatedCaseResult`
- **THEN** `result.usd` SHALL equal `0.03` (sum: `0.01 × 3`)

#### Scenario: generate_scoreboard total_usd correctly sums usd fields under repeats=3

- **GIVEN** a results file with two non-skipped cases each having `usd=0.03` (sum of 3 runs) and `repeats=3`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the output SHALL contain `Total USD: $0.0600`
