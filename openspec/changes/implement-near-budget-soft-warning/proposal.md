## Why

`budget` in case YAML is enforced as a hard cliff: a case using 95% of its `steps`/`usd`/`seconds` budget shows up identical in the scoreboard to one using 5%. There is no early warning when a case is approaching its budget cap, so the only signal a regression provides is the case flipping from `succeeded` to `timeout` (or `blocked`) — by which point the case has already crossed the cliff and the cost has already been paid. Ticket #40 (filed in plan migration) calls for a `near_budget` soft-warning flag exposed in results JSON and rendered as a "⚠️" annotation in the scoreboard so a regression that climbs from 70% → 85% of budget is visible before it tips over the limit.

## What Changes

- `task2/scripts/eval.py::CaseResult` gains a `near_budget: bool = False` field.
- `task2/scripts/eval.py::_run_case` computes `near_budget` from the loop's observed `steps`, `usd`, and `latency_ms_total` against the case's `budget` dict: `True` if any of `steps / budget.steps`, `usd / budget.usd`, or `latency_ms_total / 1000 / budget.seconds` is `≥ 0.80`. Computed only on passing-status cases (`succeeded`, `unverified`); failed/blocked/timeout/skipped cases SHALL have `near_budget = False`.
- A small helper `_is_near_budget(steps: int, usd: float, latency_ms_total: int, budget: dict) -> bool` encapsulates the threshold logic and is unit-tested directly.
- `task2/scripts/score.py::_render_case_status` appends "⚠️" to the rendered status cell when `case.get("near_budget", False)` is True. The flag is treated as additive to the existing status rendering (single-run plain status, multi-run fractional `M/N ✓`).
- Tests:
  - `test_eval.py`: a `_run_case` synthetic at 80% step budget (`steps=4, budget.steps=5`) on a `succeeded` `RunResult` yields `near_budget=True`; at 79% (`steps=3`) yields `False`; failed-status cases yield `False` regardless of how close they got.
  - `test_eval.py`: usd-axis and seconds-axis variants — each axis individually trips the flag at ≥80%.
  - `test_score.py`: a synthetic results dict with `near_budget=True` renders "⚠️" in the per-case Status cell; without it does not.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `eval-runner`: the Results JSON schema gains a `near_budget: bool` per-case field, computed from the case's observed metrics vs its declared `budget` cap.
- `score-script`: the per-case Status cell SHALL render a "⚠️" suffix when `near_budget` is True.

## Impact

- `task2/scripts/eval.py`: `CaseResult` field added; `_run_case` returns the new field; helper `_is_near_budget` added.
- `task2/scripts/score.py`: `_render_case_status` appends "⚠️" when `near_budget=True`.
- `task2/tests/test_eval.py`: new tests for the helper and `_run_case` propagation across all three axes and the failed-status guard.
- `task2/tests/test_score.py`: new test for "⚠️" rendering.
- No breaking changes: the new field defaults to `False`, so old results JSONs without the key render unchanged.
- No new dependencies; pure Python arithmetic on existing fields.
