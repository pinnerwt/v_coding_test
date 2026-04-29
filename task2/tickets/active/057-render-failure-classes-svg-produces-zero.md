---
id: 57
slug: render-failure-classes-svg-produces-zero
status: active
tier: 2
urgency: P3
axes:
  pass_rate: 0
  tokens_pct: 0
  latency_pct: 0
dependencies: []
pre_flight_gates: []
evidence: []
related: []
filed_pr: null
merged_pr: null
archived_at: null
trigger: 'surfaced by review subagent on PR #83 (iteration 2); deferred from `implement-failure-clustering-histogram`
  because spec scenarios use `n == 2`.'
---

57. **`render_failure_classes_svg` produces zero-width polygons for single-run benchmarks.** With `len(runs) == 1`, `x_at(0)` returns a single x position, and the resulting polygon has only two distinct points (top + bottom on the same x), which renders as a zero-area shape that is invisible in browsers. The cumulative-stacking math is still correct (validated by `task2/tests/test_trends.py::test_render_failure_classes_svg_polygons_are_cumulatively_stacked`), but the visual fallback for single-run benchmarks shows nothing. Decision needed: (a) short-circuit to `_empty_svg("Failure classes")` when `n < 2` since stacked-area is meaningless for a single point, (b) fall back to bar-style rendering similar to `_bar_chart_svg` when `n == 1`, or (c) widen the polygon to a thin filled rectangle around `x_at(0)` so a single-run chart shows the stacks. Tests: a 1-run, 2-class call to `render_failure_classes_svg` produces an SVG that either matches the chosen empty placeholder OR contains visible non-zero-area shapes (assert via SVG geometry, not just point-string presence). *Why useful:* the very first run on a fresh branch has `n == 1` until the second push lands, so the trend chart is silently blank for first-run PRs. *Trigger:* surfaced by review subagent on PR #83 (iteration 2); deferred from `implement-failure-clustering-histogram` because spec scenarios use `n == 2`.
