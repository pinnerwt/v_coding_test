## 1. Red — failing tests

- [x] 1.1 In `task2/tests/test_trends.py`, add `test_render_failure_classes_svg_single_run_polygons_have_nonzero_area`: build a 1-run, 2-class call (`runs = [_make_run("b1", "...", 0.0)]`, `class_counts = [{"alpha": 2, "beta": 3}]`), invoke `render_failure_classes_svg(runs, class_counts)`, regex-extract every `<polygon points="...">`, parse each point string into `[(x, y), ...]`, compute the absolute shoelace area, and assert the area is `> 0` for *every* polygon.
- [x] 1.2 Run `cd task2 && uv run pytest tests/test_trends.py::test_render_failure_classes_svg_single_run_polygons_have_nonzero_area -x` — confirm it FAILS with `area == 0` (current behavior produces collapsed polygons).
- [x] 1.3 Update `test_render_failure_classes_svg_polygons_are_cumulatively_stacked`: replace the `x0 = _PAD_L + plot_w / 2` single-x assertion with assertions against the new widened corners. Compute `bar_half = plot_w * 0.15`, `x_left = x0 - bar_half`, `x_right = x0 + bar_half`. Assert each cumulative y-coordinate appears at *both* `x_left` and `x_right` in the corresponding polygon's point string. The cumulative-stacking math (the y values themselves) is unchanged — only the x positions widen.
- [x] 1.4 Run `cd task2 && uv run pytest tests/test_trends.py::test_render_failure_classes_svg_polygons_are_cumulatively_stacked -x` — confirm it FAILS (the new x-coordinate assertions don't match the current single-x output).

## 2. Green — minimal implementation

- [x] 2.1 In `task2/scripts/trends.py::render_failure_classes_svg`, after `y_max = y_max_raw * 1.15` and the existing `x_at` definition, add a `bar_half = plot_w * 0.15` constant and a helper that yields the per-column x-coordinate list: when `n == 1`, the columns are `[x_at(0) - bar_half, x_at(0) + bar_half]`; when `n >= 2`, the columns are `[x_at(i) for i in range(n)]`.
- [x] 2.2 In the `for cls in all_classes` block, replace the `top_pts = " ".join(f"{x_at(i):.2f},{y_at(v):.2f}" for i, v in enumerate(top_vals))` line and its bottom-pts companion with logic that uses the column-x list. For `n == 1`, both columns share the same per-class y values (the same single class_count[0] entry), so the polygon has 4 corners (top-left, top-right, bottom-right, bottom-left) and renders as a rectangle. For `n >= 2`, behavior is unchanged.
- [x] 2.3 Run `cd task2 && uv run pytest tests/test_trends.py -x` — confirm the two tests from §1 now pass and all other failure-classes tests (basic, empty, deterministic-colors, write_trends-writes, readme-row) still pass.

## 3. Full suite

- [x] 3.1 Run `cd task2 && uv run pytest` — confirm no regressions across the whole suite.

## 4. Clean — lint and format

- [x] 4.1 `cd task2 && uv run ruff check --fix .`.
- [x] 4.2 `cd task2 && uv run ruff format .`.
- [x] 4.3 `cd task2 && uv run ruff check .` — confirm zero errors, zero warnings.
- [x] 4.4 `cd task2 && uv run pytest` — confirm green bar after formatting.
