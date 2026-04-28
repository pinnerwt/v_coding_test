## Context

`scripts/score.py::generate_scoreboard` currently reads per-case dicts from a results JSON and emits a markdown scoreboard with suite summaries, a per-case table, and aggregate statistics. `CaseResult.step_breakdown` (specified in `loop-metrics` and `eval-runner` specs, implemented in ticket #20) already populates a list of per-step dicts with keys `step`, `latency_ms`, `prompt_tokens`, `completion_tokens`, `usd`, `tool_calls`. The scoreboard consumes only totals (`prompt_tokens`, `completion_tokens`, `latency_ms_total`, `usd`) and never reads `step_breakdown`.

Ticket #38 requests surfacing this data in the scoreboard output so reviewers can identify step-level anomalies (token spikes, latency stalls) without replaying the full trace.

## Goals / Non-Goals

**Goals:**
- Add `--detail` flag to `score.py` CLI. When passed, emit a per-step markdown table inline after each failing case.
- When `--detail` is NOT passed, still emit a collapsible `<details>` block for failing cases that have a non-empty `step_breakdown`, so the scoreboard file is always self-contained but not visually noisy.
- Backward-compatible: old results files with no `step_breakdown` key (or empty list) produce no extra output.
- Cover both behaviors with TDD tests before touching `score.py`.

**Non-Goals:**
- Modifying the results JSON schema, `CaseResult`, `eval.py`, or `benchmark.py`.
- Emitting step breakdowns for passing or skipped cases (only failing cases are diagnostic targets).
- Sorting, filtering, or annotating individual steps (e.g. flagging the "worst" step). Plain tabular output is sufficient.
- Rendering step breakdowns in the README splice path (`--update-readme`); the scoreboard string already contains them, so the splice inherits them naturally.

## Decisions

### Decision: `--detail` flag default is OFF; collapsible block always-on for failing cases

**Rationale**: The raw table is wide and verbose — adding it unconditionally to every scoreboard (e.g. in README) would obscure the suite summary. The `<details>` collapse keeps the scoreboard file self-contained for anyone who opens it in a GitHub markdown renderer without requiring the flag. CI scripts that just check pass/fail and diff pass-rates do not need the detail rows and should not have their diffing broken by wide tables.

**Alternative considered**: Always-on without collapsing (no `--detail` flag). Rejected because the table is wide (5 columns × N steps) and will break side-by-side diffs in PR reviews when N ≥ 5.

**Alternative considered**: `--detail` only, no collapsible block in default mode. Rejected because the scoreboard file would then have zero step-level data unless the operator remembers to pass `--detail`, making the file less useful as a standalone artifact.

### Decision: Only failing cases get step breakdown tables

**Rationale**: The diagnostic value is in failures — passing cases that used 10× tokens still passed, so the "leak" is tolerable. Emitting tables for all cases would double or triple the scoreboard size for typical suites. The ticket explicitly says "for each failing case."

**Alternative considered**: All non-skipped cases. Rejected for size reasons above.

### Decision: Step breakdown helper is a standalone function `_render_step_breakdown(steps: list[dict]) -> str`

**Rationale**: Isolates the rendering logic for unit testing independent of the full `generate_scoreboard` call. The helper returns a markdown string (the table header + rows, or an empty string if `steps` is empty) so callers can wrap it in `<details>` or emit it inline.

### Decision: `tool_calls` list collapsed to a single comma-joined string in the table

**Rationale**: Most steps have exactly one tool call. Displaying a list literal (`['goto', 'done']`) would break the markdown pipe-table cell. Comma-joining gives a compact, human-readable representation.

### Decision: `<details>` block wrapping — emitted when `step_breakdown` is non-empty and status is failing, regardless of `--detail`

**Rationale**: The `<details>` approach is idiomatic GitHub markdown and requires zero extra flags from the operator. The block is collapsed by default so it does not pollute CI diffs. When `--detail` is passed, the inline table replaces the `<details>` block (not both).

## Risks / Trade-offs

- [Risk] `step_breakdown` may be absent or `null` in very old results files. → Mitigated by `case.get("step_breakdown") or []` with an empty-list fallback; no output is emitted for empty lists.
- [Risk] `<details>` blocks in markdown tables are not part of standard CommonMark and may render differently in some viewers (e.g. plain-text pagers). → Acceptable; the primary render target is GitHub markdown.
- [Risk] Wide tables (many steps) may break column alignment in terminal output. → Acceptable tradeoff; `--detail` is opt-in so terminal users who do not want the table do not pass the flag.

## Open Questions

None blocking implementation. The `<details>` always-on behavior for default mode and the inline table for `--detail` mode are the chosen direction.
