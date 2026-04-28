## Why

Ticket #31 landed `failure_class` on every failed `CaseResult`, but there is no aggregate view: contributors reading a scoreboard still have to manually count classes across rows. A histogram at the top of the scoreboard and a stacked-area trend chart make multi-failure patterns immediately visible and allow regression bisect at the class level.

## What Changes

- `task2/scripts/score.py` — `generate_scoreboard(data)` emits a `**Failure histogram**` table (two columns: `Failure class | Count`, sorted desc-by-count, ties alphabetical) after the category summary block and before the per-case status table. The block is suppressed entirely when no failed cases exist.
- `task2/scripts/trends.py` — `write_trends(...)` writes an additional SVG `task2/benchmark/_trends/failure_classes.svg` as a stacked-area chart showing per-class failure counts across runs (one series per `failure_class` value observed across the full run history).
- `task2/README.md` — the `<!-- TRENDS:BEGIN -->` block gains a fourth image row pointing at `_trends/failure_classes.svg`, inserted after the cost chart row.
- `task2/tests/test_score.py` and `task2/tests/test_trends.py` — new tests covering histogram rendering, suppression, sort order, SVG emission, and README block update (TDD red-green cycle per repo convention).
- Golden-snapshot fixture `task2/tests/fixtures/results/sample_results_scoreboard.md` updated to include the new histogram block.

## Capabilities

### New Capabilities

None — both changed files already have capability specs.

### Modified Capabilities

- `score-script`: New requirement `Failure histogram block` (section-order list also extended to insert the histogram between category summary and per-case table).
- `trends-regression-flag`: New requirement `failure_classes stacked-area SVG` covering the new chart and the README row it adds. The existing `trends-regression-flag` spec is the only spec that covers `task2/scripts/trends.py`, so this delta lands there.

## Impact

- Scoreboard layout: one new section (histogram) between category summary and per-case table. Existing section order is preserved; nothing is removed.
- One new SVG artifact checked into `task2/benchmark/_trends/failure_classes.svg`.
- `task2/README.md` gains one image link inside the existing TRENDS block.
- No API or schema changes; `failure_class` is already serialised in `results.json` by #31.
- Backward-compatible: result files without `failure_class` (or with `null`) silently produce no histogram rows.
