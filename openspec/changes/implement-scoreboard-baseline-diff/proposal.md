## Why

PR reviews and CI runs produce a scoreboard for the current branch, but there is no automatic comparison against the `master` baseline — a reviewer must diff the two scoreboard files by hand to spot regressions. Ticket #36 closes this gap by making the benchmark machinery emit a structured "Δ vs master" diff whenever it runs on a non-master branch, and by wiring CI to post that diff as a PR comment.

## What Changes

- **New module `task2/scripts/baseline_diff.py`** — pure function `generate_diff_markdown(master: dict, branch: dict) -> str` that computes per-case status deltas (newly-passing, newly-failing, unchanged), aggregate pass-rate delta, total USD delta, and p50/p95 latency delta.
- **`task2/scripts/benchmark.py` extended** — after writing `results.json` / `scoreboard.md`, when branch ≠ master and `task2/benchmark/master/results.json` exists, load it and call `generate_diff_markdown`; write the result to `task2/benchmark/<branch>/diff.md`.
- **`task2/scripts/score.py` extended** — new `--diff` flag (optional path to a baseline results JSON) that appends the diff table to the scoreboard output in addition to the standalone `diff.md`.
- **`.github/workflows/task2-benchmark.yml` extended** — new step after the verify step: if `task2/benchmark/<branch>/diff.md` exists, post it as a PR comment (using `gh pr comment --edit-last`).
- **New tests** — synthetic master + branch results pairs exercise all delta scenarios (newly-passing, newly-failing, unchanged, no-op, missing master file).

## Capabilities

### New Capabilities
- `baseline-diff`: Diff renderer that compares two benchmark results.json files and emits a structured Δ vs master markdown table with regression severity.

### Modified Capabilities
- `score-script`: New `--diff` flag that accepts an optional baseline results path and appends the diff block to the scoreboard output.

## Impact

- `task2/scripts/baseline_diff.py` (new file)
- `task2/scripts/benchmark.py` (write `diff.md` after benchmark run)
- `task2/scripts/score.py` (new `--diff` flag)
- `.github/workflows/task2-benchmark.yml` (new step to post PR comment)
- `task2/tests/` (new test file for diff scenarios)
- `task2/benchmark/<branch>/diff.md` (new output artifact written per branch)
- No changes to the `results.json` schema; no new dependencies expected (diff logic is pure Python).
