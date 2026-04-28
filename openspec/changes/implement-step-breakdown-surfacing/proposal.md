## Why

`CaseResult.step_breakdown` (introduced in ticket #20) already records per-step token counts, tool calls, and latency, but `scripts/score.py` surfaces only suite-level totals — making it invisible when a single step consumes 10× the average tokens (e.g. AX-tree observation balloons) or stalls for >30 s on a fast page (Playwright timeout). Adding a `--detail` flag exposes these per-step signals directly in the scoreboard output so reviewers can pinpoint the offending step without replaying the full trace.

## What Changes

- **New `--detail` flag** on `scripts/score.py` (default off). When passed, `generate_scoreboard` appends a per-step breakdown table after each failing (non-skipped, non-passing) case's row in the scoreboard.
- **Per-step table format**: one row per `step_breakdown` entry with columns `Step`, `Tool`, `Prompt Tokens`, `Completion Tokens`, `Latency (ms)`. The table is emitted inline (not collapsed) when `--detail` is active.
- **Collapsible `<details>` block** (always-on for markdown render contexts): when `--detail` is NOT passed, failing cases with a non-empty `step_breakdown` still emit a `<details><summary>step breakdown</summary>…</details>` block so the scoreboard file is always self-contained but the table is hidden by default.
- **Backward-compatible**: cases with no `step_breakdown` (empty list or field absent) silently produce no table; old results files work unchanged.
- **New tests**: two TDD scenarios — one asserting the table is present and correctly formatted under `--detail`, one asserting the collapsible block appears in default mode.

## Capabilities

### New Capabilities

*(none — this change extends an existing capability only)*

### Modified Capabilities

- `score-script`: Two new requirements added — the `--detail` CLI flag and the per-step breakdown table rendering logic (inline under `--detail`, collapsed `<details>` block otherwise).

## Impact

- `task2/scripts/score.py`: `main()` gains `--detail` argument; `generate_scoreboard` gains a helper `_render_step_breakdown_table(steps: list[dict]) -> str` and logic to emit per-step tables for failing cases.
- `task2/tests/test_score.py` (or a new `test_score_detail.py`): two new TDD tests.
- No new dependencies; no changes to `eval.py`, `benchmark.py`, `CaseResult`, or the results JSON schema.
- Existing `--output` and `--update-readme` flags are unaffected; the per-step tables are part of the generated scoreboard string and therefore included when those flags are used.
