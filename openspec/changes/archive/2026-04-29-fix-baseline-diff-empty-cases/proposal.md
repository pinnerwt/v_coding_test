## Why

`baseline_diff.py::generate_diff_markdown` silently emits `Δ pass-rate: +0%`, `Δ total USD: +$0.0000`, and `Δ p50/p95 latency: +0ms` when either the master or branch run has zero runnable (non-skipped) cases (`m_ran == 0` or `b_ran == 0`). A reviewer reading `+0%` infers "no regression" when the truth is "no signal at all". This is a high-confusion failure mode at PR-review time, surfaced by review subagent on PR #76.

## What Changes

- `task2/scripts/baseline_diff.py` — modify `generate_diff_markdown` so that when either side has zero runnable cases, each affected aggregate line emits `n/a (<reason>)` instead of a misleading numeric delta.
- `task2/tests/test_baseline_diff.py` — add synthetic tests: master with `cases: []` paired with a non-empty branch (and vice versa), asserting that each aggregate line shows `n/a` and includes the reason string.
- No changes to any other script (`benchmark.py`, `score.py`, `eval.py`, `trends.py`); no new CLI flags; no new CaseResult fields.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `baseline-diff`: The aggregate block rendering in `generate_diff_markdown` now emits `n/a (<reason>)` for `Δ pass-rate`, `Δ total USD`, `Δ p50 latency`, and `Δ p95 latency` when either side has zero runnable cases, rather than `+0%` / `+$0.0000` / `+0ms`.

## Impact

- `task2/scripts/baseline_diff.py`: aggregate delta lines change output format in the empty-side edge case.
- `task2/tests/test_baseline_diff.py`: new tests; existing passing tests are unaffected (they use non-empty fixtures).
- No breaking changes for the normal (both sides non-empty) code path.
- No new dependencies.
