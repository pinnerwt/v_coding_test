## ADDED Requirements

### Requirement: Skipped subsection with reason counts
`generate_scoreboard()` SHALL append a "Skipped" subsection to the scoreboard output when at least one case has `status="skipped"`. The subsection SHALL appear after the per-case table rows (and the blank line following them) but before the aggregate summary line.

The subsection SHALL render as:

```
**Skipped** (<total_skipped> cases)

| Skip reason | Count |
|---|---|
| live_disabled | <N> |
| fixture_missing | <N> |
```

- Only reasons that appear in the results (count ≥ 1) SHALL be included as rows.
- Reasons SHALL be listed in the following canonical order: `live_disabled`, `infra_unavailable`, `fixture_missing`, `feature_not_implemented`. Reasons not present in results are omitted entirely.
- `skip_reason` values that are `None` (e.g. from old result files lacking the field) SHALL be treated as if the case was not skipped for counting purposes — they SHALL NOT appear as a `None` row.
- When no cases are skipped, the "Skipped" subsection SHALL be omitted entirely.

#### Scenario: Skipped subsection appears when skip_reason is present
- **GIVEN** a results file with one case having `status="skipped"` and `skip_reason="live_disabled"`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the output SHALL contain a line matching `**Skipped** (1 cases)`
- **AND** the output SHALL contain a row `| live_disabled | 1 |`

#### Scenario: Multiple skip reasons are each counted separately
- **GIVEN** a results file with two skipped cases: one `live_disabled` and one `fixture_missing`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the output SHALL contain `| live_disabled | 1 |` and `| fixture_missing | 1 |`
- **AND** the header line SHALL read `**Skipped** (2 cases)`

#### Scenario: No skipped cases omits the subsection entirely
- **GIVEN** a results file with no cases having `status="skipped"`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the output SHALL NOT contain the string `**Skipped**`

#### Scenario: Skipped subsection appears before aggregate summary line
- **GIVEN** a results file with at least one skipped case
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the position of `**Skipped**` in the output string SHALL be less than the position of the aggregate summary line (the `**N/M succeeded` line)

#### Scenario: Old result files without skip_reason field produce no Skipped subsection
- **GIVEN** a results file whose case entries have no `skip_reason` key
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** no `**Skipped**` section SHALL appear and no exception SHALL be raised
