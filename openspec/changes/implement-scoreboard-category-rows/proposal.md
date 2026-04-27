## Why

The scoreboard currently shows only aggregate totals, making it impossible to tell at a glance whether the drift, fixture, or live suites are individually passing their Done-bar thresholds. Ticket #33 requires per-suite pass-rate rows with traffic-light indicators surfaced above the per-case table so reviewers can immediately see suite health against the defined targets (drift 100%, fixture 80%, live 60%).

## What Changes

- `task2/scripts/score.py` gains a module-level `SUITE_THRESHOLDS` config block mapping suite keys to `name`, `id_prefixes`, and `target_pct`.
- `generate_scoreboard()` is extended to prepend a **category summary table** above the existing per-case table. Each row shows: suite name, passed/ran count, percentage, target, and a traffic-light symbol (✅ / ❌ / ⏭️).
- Cases are bucketed into suites by matching their `id` field against `id_prefixes` in `SUITE_THRESHOLDS`; unmatched cases fall into an "other" bucket with no threshold.
- A new vendored fixture `task2/tests/fixtures/score_categories_results.json` is authored to drive the new tests.
- New tests in `task2/tests/test_score.py` assert the exact category summary lines rendered by `generate_scoreboard()`.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `score-script`: The `score.py reads a results JSON and emits a markdown scoreboard` requirement gains new scenarios for category aggregation and traffic-light rendering. A new requirement for the suite-threshold config block is added.

## Impact

- `task2/scripts/score.py` — additive changes only; existing per-case table, summary line, percentiles, totals, tier mix, and mechanism rates are untouched.
- `task2/tests/test_score.py` — new test functions added.
- `task2/tests/fixtures/score_categories_results.json` — new vendored fixture file.
- No API, CLI interface, or README sentinel format changes.
