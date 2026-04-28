## Why

The benchmark trend SVGs recorded by `task2/scripts/trends.py` show pass-rate degrading from ~38 % (peak, `task2-fix-llm-model-default`) down to 0 % on the three most-recent branches, with no ticket explaining the drop. Without an automated warning in the `<!-- TRENDS:BEGIN -->` block and a per-case regression-onset artifact, the trend charts are noise rather than signal — actionable regressions go unnoticed.

## What Changes

- **New behavior in `task2/scripts/trends.py`**: when the latest run's pass-rate is more than 5 percentage-points below the running median of all recorded runs, emit a `⚠️` warning on the latest-run row inside the `<!-- TRENDS:BEGIN … TRENDS:END -->` block in `task2/README.md` (already the block updated by `write_trends`).
- **New function `flag_regression(runs) -> bool`** (pure, no I/O) in `trends.py`: returns `True` when the latest run's pass-rate is below the median of all run pass-rates by more than `REGRESSION_THRESHOLD_PP = 5`.
- **New test in `task2/tests/test_trends.py`**: deterministic 3-run synthetic series with monotonically degrading pass-rate asserts the warning is emitted in the rendered README block.
- **New script `task2/scripts/regression_onset.py`**: reads all `task2/benchmark/*/results.json` in `run_at` order, computes the first branch where each case flipped pass→fail and stayed failing, and writes `task2/benchmark/_trends/regression_onset.md`.
- **Generated artifact `task2/benchmark/_trends/regression_onset.md`**: checked-in output of a single `uv run python -m scripts.regression_onset` run; regenerated whenever a new benchmark run is added.

## Capabilities

### New Capabilities
- `trends-regression-flag`: detection and rendering of a pass-rate regression warning inside the `<!-- TRENDS:BEGIN -->` block, plus the `flag_regression()` helper and its test.
- `regression-onset-report`: the `regression_onset.py` script and its `regression_onset.md` output artifact.

### Modified Capabilities
_(none — the existing `score-script` spec controls `score.py`; `trends.py` requirements live in the new `trends-regression-flag` spec since no prior trends-behavior spec existed)_

## Impact

- `task2/scripts/trends.py` — add `flag_regression()`, update `_render_readme_block()` to call it and inject the `⚠️` badge.
- `task2/tests/test_trends.py` — add one deterministic regression-flag test.
- `task2/scripts/regression_onset.py` — new script (~80 lines).
- `task2/benchmark/_trends/regression_onset.md` — new generated artifact, checked in.
- No changes to `score.py`, `benchmark.py`, or any eval-runner paths.

## Investigation findings (narrative, not code scope)

Across 22 recorded benchmark runs the pass-rate is highly volatile (0–50 %) because:

1. **Qwen endpoint stochasticity (driver c)** — `fixture-heading` and `fixture-count` flip pass/fail across consecutive runs on the same branch content, indicating the LLM output varies per invocation.
2. **Case count expansion (driver a, benign)** — `task2-implement-self-correction-proof` added 4 new fixture cases that all fail, diluting the denominator from 4 to 8 non-skipped cases.
3. **Two definite regressions with onset SHAs**:
   - `fixture-count`: onset branch `task2-implement-observe-ax-tree` (2026-04-26T16:18). Previously passed on `feat-task2-benchmark-per-pr`.
   - `fixture-heading`: onset branch `task2-implement-plan-event-trace-writer` (2026-04-27T05:33). Previously passed on `task2-implement-loop-multi-tool-last-action`.
4. **No evidence of driver (e)** (`--repeats` math bug) — all failing runs used `--repeats 1`.

The automated `regression_onset.md` captures these findings in a git-bisectable form. The `flag_regression()` warning ensures future dips are caught immediately.
