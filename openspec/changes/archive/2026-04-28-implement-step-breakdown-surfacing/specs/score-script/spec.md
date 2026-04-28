## ADDED Requirements

### Requirement: score.py --detail flag emits per-step breakdown table inline for failing cases

`scripts/score.py` SHALL accept an optional `--detail` boolean flag (default `False`). When `--detail` is passed:

- For each case in the scoreboard whose status is NOT `"succeeded"`, `"unverified"`, or `"skipped"` (i.e. failing cases), `generate_scoreboard` SHALL emit a per-step markdown table immediately after that case's row in the per-case table. The table SHALL NOT be emitted for passing or skipped cases.
- The table SHALL have the following columns (in order): `Step`, `Tool`, `Prompt Tokens`, `Completion Tokens`, `Latency (ms)`.
- Each row in the table SHALL correspond to one entry in `case["step_breakdown"]`, in the order returned by the results JSON (`step_breakdown[0]` → row 1, etc.).
- The `Tool` column SHALL be populated by joining `step["tool_calls"]` with `", "` (comma-space). When `tool_calls` is empty, the cell SHALL contain `"-"`.
- When `step_breakdown` is absent, `None`, or an empty list for a failing case, no table SHALL be emitted for that case (silent no-op).
- When `--detail` is passed, the inline table SHALL replace the collapsible `<details>` block for that case (only one form is emitted per case, not both).
- `generate_scoreboard` SHALL accept an optional `detail: bool = False` keyword argument so callers can pass it programmatically without going through `main()`.

#### Scenario: --detail flag produces per-step table for failing case

- **GIVEN** a results file with one failing case (`status="failed"`) whose `step_breakdown` has two entries: `[{"step": 1, "tool_calls": ["goto"], "prompt_tokens": 120, "completion_tokens": 15, "latency_ms": 800}, {"step": 2, "tool_calls": ["done"], "prompt_tokens": 200, "completion_tokens": 30, "latency_ms": 1200}]`
- **WHEN** `generate_scoreboard(data, detail=True)` is called
- **THEN** the output SHALL contain a markdown table with header `| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |`
- **AND** the output SHALL contain a row matching `| 1 | goto | 120 | 15 | 800 |`
- **AND** the output SHALL contain a row matching `| 2 | done | 200 | 30 | 1200 |`

#### Scenario: --detail flag produces no table for passing case

- **GIVEN** a results file with one passing case (`status="succeeded"`) whose `step_breakdown` is non-empty
- **WHEN** `generate_scoreboard(data, detail=True)` is called
- **THEN** the output SHALL NOT contain the string `Prompt Tokens` in the context of a per-step table for that passing case

#### Scenario: --detail flag produces no table when step_breakdown is empty

- **GIVEN** a results file with one failing case (`status="failed"`) whose `step_breakdown` is `[]` (empty list)
- **WHEN** `generate_scoreboard(data, detail=True)` is called
- **THEN** no per-step table header (`Step | Tool | Prompt Tokens`) SHALL appear in the output

#### Scenario: --detail flag is forwarded from main() to generate_scoreboard

- **GIVEN** `score.py` is invoked as `score.py <results_file> --detail`
- **WHEN** `main()` parses the argument
- **THEN** `generate_scoreboard` SHALL be called with `detail=True`

#### Scenario: tool_calls list is comma-joined in the Tool column

- **GIVEN** a failing case whose `step_breakdown` has one entry with `tool_calls: ["click", "read"]`
- **WHEN** `generate_scoreboard(data, detail=True)` is called
- **THEN** the Tool column cell for that step SHALL contain `click, read`

#### Scenario: empty tool_calls list renders as dash in the Tool column

- **GIVEN** a failing case whose `step_breakdown` has one entry with `tool_calls: []`
- **WHEN** `generate_scoreboard(data, detail=True)` is called
- **THEN** the Tool column cell for that step SHALL contain `-`

### Requirement: score.py emits collapsible step breakdown block for failing cases in default mode

When `--detail` is NOT passed (the default), `generate_scoreboard` SHALL emit a collapsible `<details>` block immediately after each failing case's per-case table row when that case has a non-empty `step_breakdown`. The block SHALL:

- Open with `<details><summary>step breakdown (N steps)</summary>` where `N` is `len(step_breakdown)`.
- Contain the same per-step markdown table (columns `Step`, `Tool`, `Prompt Tokens`, `Completion Tokens`, `Latency (ms)`) as the `--detail` inline form.
- Close with `</details>`.
- Be omitted entirely when `step_breakdown` is absent, `None`, or empty.
- Be omitted for passing (`succeeded`, `unverified`) and skipped cases regardless of `step_breakdown` content.
- NOT be emitted when `--detail` is active (inline table takes precedence).

The `_render_step_breakdown(steps: list[dict]) -> str` helper SHALL be defined in `scripts/score.py` and return the markdown table string (header + rows) for the given list of step dicts. It SHALL return an empty string when `steps` is empty. Callers are responsible for wrapping the result in `<details>` or emitting it inline.

#### Scenario: default mode emits collapsible block for failing case with step_breakdown

- **GIVEN** a results file with one failing case (`status="failed"`) whose `step_breakdown` has three entries
- **WHEN** `generate_scoreboard(data)` is called without `detail=True`
- **THEN** the output SHALL contain `<details><summary>step breakdown (3 steps)</summary>`
- **AND** the output SHALL contain `</details>`
- **AND** the output SHALL contain a markdown table with `| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |` inside the block

#### Scenario: default mode does not emit block for passing case

- **GIVEN** a results file with one passing case (`status="succeeded"`) whose `step_breakdown` is non-empty
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** the output SHALL NOT contain `<details>` related to a step breakdown for that passing case

#### Scenario: default mode does not emit block when step_breakdown is absent

- **GIVEN** a results file with one failing case whose dict has no `step_breakdown` key
- **WHEN** `generate_scoreboard(data)` is called
- **THEN** no `<details>` block SHALL appear in the output
- **AND** no exception SHALL be raised

#### Scenario: _render_step_breakdown returns empty string for empty list

- **GIVEN** `_render_step_breakdown([])` is called
- **WHEN** the function returns
- **THEN** the result SHALL be an empty string `""`

#### Scenario: _render_step_breakdown returns table for non-empty list

- **GIVEN** `_render_step_breakdown([{"step": 1, "tool_calls": ["goto"], "prompt_tokens": 100, "completion_tokens": 10, "latency_ms": 500}])` is called
- **WHEN** the function returns
- **THEN** the result SHALL contain the header `| Step | Tool | Prompt Tokens | Completion Tokens | Latency (ms) |`
- **AND** the result SHALL contain a row with `1`, `goto`, `100`, `10`, `500`

#### Scenario: collapsible block is not emitted when --detail is active

- **GIVEN** a results file with one failing case with a non-empty `step_breakdown`
- **WHEN** `generate_scoreboard(data, detail=True)` is called
- **THEN** the output SHALL NOT contain `<details>` for that case's step breakdown
- **AND** the inline table SHALL be present instead
