## Why

The per-case scoreboard table exposes cache invalidation counts but hides whether the cache is actually serving traffic: a case with `Cache Inv.=0` could mean a warm, hit-serving cache or a permanently cold one. Adding `Cache Hits` and `Cache Misses` columns gives reviewers the signal they need to distinguish "cache is working" from "cache is always cold" — directly supporting the brief's requirement to demonstrate self-maintenance mechanisms.

`cache_events.{hits, misses, invalidations}` are already aggregated by `_aggregate_diagnostics` per ticket #29 and stored in `CaseResult.cache_events`. No new instrumentation is needed — this is purely a scoreboard surfacing change.

## What Changes

- `generate_scoreboard` in `scripts/score.py` gains two new columns adjacent to `Cache Inv.`: `Cache Hits` and `Cache Misses` (convention: hits / misses / invalidations left-to-right).
- The per-case row formatter reads `cache_events.hits` and `cache_events.misses` alongside the existing `cache_events.invalidations` read.
- The table header changes from `... | Cache Inv. | Failure class |` to `... | Cache Hits | Cache Misses | Cache Inv. | Failure class |`.
- Golden snapshot `tests/fixtures/results/sample_results_scoreboard.md` must be regenerated to match the wider table.
- New tests in `task2/tests/test_score.py` assert the two new columns appear in the header and are populated correctly per-case.
- No changes to `CaseResult`, `_aggregate_diagnostics`, `eval.py`, or `baseline_diff.py` — the data is already present.

## Capabilities

### New Capabilities

_(none — this change introduces no new capability spec files)_

### Modified Capabilities

- `score-script`: The per-case table column list in **Requirement: score.py reads a results JSON and emits a markdown scoreboard** gains two new columns (`Cache Hits`, `Cache Misses`), changing the header and row format contract.

## Impact

- `task2/scripts/score.py` — header string and row formatter updated.
- `task2/tests/test_score.py` — new tests for the two new columns; existing assertions on `Cache Inv.` remain unchanged.
- `task2/tests/fixtures/results/sample_results_scoreboard.md` — golden snapshot regenerated after implementation.
- No impact on `eval.py`, `baseline_diff.py`, `CaseResult`, or `_aggregate_diagnostics`.
