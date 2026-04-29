## MODIFIED Requirements

### Requirement: score.py reads a results JSON and emits a markdown scoreboard

The `task2/scripts/score.py` script SHALL read the latest results JSON written by `scripts/eval.py` (selected by lexicographic max of timestamp filenames in `task2/eval/results/`) and emit a markdown scoreboard to stdout — or to `task2/eval/scoreboard.md` when invoked with `--write`. The scoreboard SHALL contain at minimum:

- A "Generated from eval run: `<run_at>`" header line.
- A category-summary block (one line per suite) appearing before the per-case table.
- A failure-histogram block (when applicable) appearing after the category summary and before the per-case table.
- A per-case table whose Status column is rendered by `_render_case_status(case: dict) -> str`.

`_render_case_status` SHALL render the per-case Status cell as follows:

1. If `case["repeat_status"] == "skipped"`: return `case.get("status", "skipped")`.
2. Otherwise, compute the base label: when `case.get("repeats", 1) > 1`, the base is `f"{passed_runs}/{repeats} {glyph}"` where `glyph = "✓"` if `passed_runs == repeats` else `"✗"`; when `repeats == 1` (or absent), the base is `case.get("status", "unknown")`.
3. When `case.get("near_budget", False)` is `True`, append `" ⚠️"` to the base label and return that string.
4. Otherwise, return the base label unchanged.

The "⚠️" suffix SHALL be additive: it composes with both the single-run plain status (e.g. `"succeeded ⚠️"`) and the multi-run fractional status (e.g. `"3/3 ✓ ⚠️"`).

#### Scenario: _render_case_status appends warning when near_budget is True (single run)

- **GIVEN** a per-case dict `{"status": "succeeded", "near_budget": True}`
- **WHEN** `_render_case_status(case)` is called
- **THEN** the returned string SHALL contain `"⚠️"`
- **AND** the returned string SHALL also contain `"succeeded"`

#### Scenario: _render_case_status omits warning when near_budget is False

- **GIVEN** a per-case dict `{"status": "succeeded", "near_budget": False}`
- **WHEN** `_render_case_status(case)` is called
- **THEN** the returned string SHALL NOT contain `"⚠️"`

#### Scenario: _render_case_status omits warning when near_budget key is absent

- **GIVEN** a per-case dict `{"status": "succeeded"}` (no `near_budget` key, simulating an old results JSON)
- **WHEN** `_render_case_status(case)` is called
- **THEN** the returned string SHALL NOT contain `"⚠️"`

#### Scenario: _render_case_status appends warning to multi-run fractional status

- **GIVEN** a per-case dict `{"status": "succeeded", "repeats": 3, "passed_runs": 3, "near_budget": True}`
- **WHEN** `_render_case_status(case)` is called
- **THEN** the returned string SHALL contain `"3/3"` AND `"⚠️"`
