## Context

Ticket #31 added `failure_class` (values: `tool_error`, `locator_miss`, `supervisor_halt`, `validator_fail`, `schema_error`, `no_done_emitted`, `other`) to every failed `CaseResult` and serialised it to `results.json`. The aggregate view is missing: the scoreboard shows the class per-row but never aggregates, and the trend charts show no per-class breakdown over time.

## Goals / Non-Goals

**Goals:**

- Insert a `**Failure histogram**` block into the scoreboard output between the category summary and the per-case table, showing class → count sorted desc-by-count (ties alphabetical).
- Suppress the block entirely when there are zero failed cases or when all `failure_class` values are `None`.
- Emit `task2/benchmark/_trends/failure_classes.svg` as a stacked-area chart (one series per class) from `write_trends`.
- Add a row for `failure_classes.svg` to the README TRENDS block (after the cost SVG row).
- Maintain backward compatibility with old `results.json` files lacking `failure_class`.

**Non-Goals:**

- Aggregating `failure_detail` strings (free-text; histogram only covers the closed `failure_class` enum).
- Any UI change to the FastAPI server or API schema.
- Modifying the classification logic itself (`_classify_failure` in `eval.py`).

## Decisions

### Histogram placement

The histogram appears immediately after the category summary lines and before the per-case table header. Rationale: it gives reviewers the "what's broken" summary before they scroll through individual rows. The existing section-order list in the `score-script` spec is extended with a new `Failure histogram` entry between `Category summary` and `Per-case status table`.

### Histogram format

```
**Failure histogram** (N failed)

| Failure class | Count |
|---|---|
| supervisor_halt | 5 |
| locator_miss | 1 |
```

The header line includes the count of failed cases for quick scanning. Rows are sorted descending by count; ties broken alphabetically by class name — ensuring a deterministic golden snapshot regardless of insertion order in the results JSON.

### Suppression rule

The block is omitted in full when `len(failed_cases) == 0`. Cases with `failure_class=None` are excluded from histogram rows (they do not produce a `None` row). If all failed cases have `failure_class=None`, the histogram renders with zero rows — which would be confusing, so the suppression condition is: omit when `sum(counts.values()) == 0` (i.e., no classifiable failures).

### Stacked-area chart for trends

The ticket text says "stacked area chart, similar to existing pass-rate / latency / cost trends." The existing chart functions use `_bar_chart_svg`, `_grouped_bar_chart_svg`, and `_line_chart_svg`. A true SVG stacked-area chart requires polygon fill-between logic not present in the current helper set. Rather than adding a general stacked-area helper for a single use case, we implement a dedicated `render_failure_classes_svg(runs_data)` function that takes a list of per-run failure-class count dicts and builds the SVG directly using filled polygons. The function signature mirrors the existing render-* functions: it takes `list[Run]` plus a parallel list of `dict[str, int]` (class → count per run), keeping the shape consistent with the existing chart API.

Color assignment is deterministic: classes are sorted alphabetically, then assigned colors from a fixed palette list (index = `sorted_classes.index(cls) % len(palette)`). This ensures the same class always gets the same color across runs.

### Run-data collection for failure_classes

`collect_runs` currently builds `Run` dataclass objects and discards the raw case lists. Rather than bloating `Run`, the new `collect_failure_class_runs` function reads `results.json` files in the same run-discovery order as `collect_runs` and returns a parallel `list[dict[str, int]]` (one dict per run, class → count). This avoids modifying the `Run` dataclass and keeps `collect_runs` unchanged.

### README TRENDS block

The new image row is appended after the cost SVG row and before the explanatory prose paragraph. The `_render_readme_block` function is updated to include the new line.

## Risks / Trade-offs

- **Color palette size**: with 7 possible failure classes the fixed palette (≥7 colors) is sufficient. If more classes are added in future, the modulo wrap is safe but may produce color collisions.
- **Stacked-area complexity**: the filled-polygon stacked area is more complex than the existing bar charts; a simpler grouped bar chart would be easier to implement but contradicts the ticket spec ("stacked area chart"). We follow the ticket spec.
- **Golden snapshot churn**: every addition to the scoreboard invalidates `sample_results_scoreboard.md`. The TDD task list includes an explicit snapshot-fixture-update task.
