## Why

`CaseResult.status="failed"` currently carries almost no signal — validators are often empty, step counts are low, and there is no narrative of what went wrong. Every other benchmark improvement (audit, per-category stats, rerun mode) is bottlenecked on knowing *why* the 6 failing cases fail. Adding structured failure classification turns silent failures into actionable data.

## What Changes

- Add `failure_class: Literal["budget_exceeded", "tool_error", "locator_miss", "supervisor_halt", "validator_fail", "schema_error", "no_done_emitted", "other"] | None` to `CaseResult` (None for passing/skipped cases).
- Add `failure_detail: str | None` to `CaseResult` (short human-readable string explaining the class, None for passing/skipped cases).
- Add `_classify_failure(events, validators, status)` private function in `scripts/eval.py` that inspects the trace event list and validator results to derive the above fields.
- Call `_classify_failure` from `_run_case` after `_aggregate_diagnostics` and populate the new fields.
- Surface `failure_class` and `failure_detail` as a new column in `scripts/score.py`'s scoreboard markdown table.

## Capabilities

### New Capabilities

- `failure-classification`: `_classify_failure` function, `CaseResult.failure_class` / `failure_detail` fields, and scoreboard column.

### Modified Capabilities

- `eval-metrics`: `CaseResult` gains two new fields (`failure_class`, `failure_detail`) with `None` defaults; the Results JSON schema gains those keys; `_run_case` calls `_classify_failure` and populates them.

## Impact

- `task2/scripts/eval.py` — adds `_classify_failure`, extends `CaseResult`, calls classification from `_run_case`.
- `task2/scripts/score.py` — scoreboard table gains a "Failure class" column.
- `task2/tests/test_eval.py` — new synthetic-trace tests covering all 8 `failure_class` values plus the passing-case None path.
- No new dependencies; no schema or DB changes; no Zeabur env var changes.
