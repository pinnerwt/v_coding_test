## ADDED Requirements

### Requirement: generate_scoreboard emits mechanism-firing columns

`scripts.score.generate_scoreboard(data: dict) -> str` SHALL be extended to include, for each case row in the per-case status table, three additional columns appended after `Tokens (P+C)`:

- `Escalations` — the count of items in `case.get("escalations", [])`.
- `Replans` — `case.get("replans", 0)`.
- `Cache Inv.` — `case.get("cache_events", {}).get("invalidations", 0)`.

The table header row SHALL be updated to include these three columns.

After the existing `| Tier | Count |` table, `generate_scoreboard` SHALL emit a "Mechanism firing rates" block:

```
| Mechanism | Cases with ≥1 firing |
|---|---|
| L1→L2 escalation | N/M |
| Replan | N/M |
| Cache invalidation | N/M |
```

where N is the count of non-skipped cases with at least one firing of that mechanism and M is the total non-skipped cases.

Existing sections (per-case table, summary line, latency percentiles, totals, tier table) SHALL remain in their current positions and format; only the three new columns and the mechanism firing rates block are added.

#### Scenario: generate_scoreboard includes mechanism columns in per-case table

- **GIVEN** a results dict with one case that has `escalations=[{"from_tier": "L1_ax", "to_tier": "L2_dom", "intent": "x", "reason": "zero_matches"}]`, `replans=0`, `cache_events={"hits": 0, "invalidations": 0, "misses": 0}`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the output SHALL contain a table row with `| 1 | 0 | 0 |` in the mechanism column positions
- **AND** the header row SHALL contain `Escalations`, `Replans`, `Cache Inv.`

#### Scenario: generate_scoreboard mechanism rates block shows correct fractions

- **GIVEN** a results dict with two non-skipped cases: one with `replans=1`, one with `replans=0`
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the output SHALL contain `| Replan | 1/2 |`

#### Scenario: generate_scoreboard is backward-compatible with cases missing new fields

- **GIVEN** a results dict with cases that have no `escalations`, `replans`, or `cache_events` keys
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the call SHALL succeed without raising an exception
- **AND** the mechanism columns SHALL default to `0`
