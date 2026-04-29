## Why

`render_failure_classes_svg` produces zero-area polygons for single-run benchmarks. With `len(runs) == 1`, the local helper `x_at(0)` returns a single x position (`_PAD_L + plot_w / 2`); the resulting polygon's top and bottom point lists collapse to two distinct points sharing that single x, which renders as an invisible zero-area shape in browsers. The cumulative-stacking math is correct (validated by `test_render_failure_classes_svg_polygons_are_cumulatively_stacked`), but the *visual* fallback for first-run-on-a-fresh-branch benchmarks is silently blank — the very moment when reviewers most need to see the failure mix.

Surfaced in ticket #57. Trigger: review subagent on PR #83 (iteration 2); deferred from `implement-failure-clustering-histogram` because spec scenarios at the time only exercised `n == 2`.

## What Changes

- `task2/scripts/trends.py::render_failure_classes_svg` — when `n == 1`, build each per-class polygon over **two** distinct x-coordinates (left and right of a thin column centered on `x_at(0)`), so the polygon has four non-collinear corners and renders as a visible rectangle. The cumulative-stacking math (per-class y values) is unchanged. For `n >= 2`, behavior is unchanged.
- `task2/tests/test_trends.py` — add `test_render_failure_classes_svg_single_run_polygons_have_nonzero_area` (new, failing-first) which parses each `<polygon>` point list, computes the geometric area via the shoelace formula, and asserts area > 0 for every per-class polygon. Update `test_render_failure_classes_svg_polygons_are_cumulatively_stacked` to assert the cumulative y-coordinates appear in the polygon point lists at the new left and right x positions (the math hasn't changed; the geometry has widened).
- No CLI changes, no new config, no behavior change for `n >= 2`, no change to `_empty_svg`, no new dependencies.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `trends-regression-flag`: the `render_failure_classes_svg` requirement gains a new scenario for `n == 1` rendering: each per-class polygon is a visible non-zero-area rectangle widened around `x_at(0)`, rather than a degenerate zero-area shape.

## Impact

- `task2/scripts/trends.py`: ~10-line change to the per-class polygon-building section of `render_failure_classes_svg`.
- `task2/tests/test_trends.py`: one new test (geometry-based), one updated test (point-string assertions widened to the new corner coordinates).
- No behavior change for `n >= 2`; existing trend-generation flows are unaffected on master.
- The first single-run trend output is now a visible stacked rectangle instead of a blank chart on the very first run of a fresh branch (runtime artifact, not a tracked file).
- No breaking changes; no new dependencies.
