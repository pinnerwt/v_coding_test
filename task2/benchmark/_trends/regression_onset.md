# Regression Onset Report

Generated: 2026-04-28T03:08:08+00:00
Benchmark root: benchmark

Branch names map to git branches via 'git log --oneline <branch> -1'.

Regenerate: `cd task2 && uv run python -m scripts.regression_onset --benchmark-root benchmark`

## Regressions

| Case | Onset Branch | Onset run_at | Prior passing branch |
|---|---|---|---|
| correction-replan | task2-fix-run-agent-traceback-logging | 2026-04-27T15:50:14.730503+00:00 | task2-fix-llm-model-default |
| fixture-count | task2-implement-observe-ax-tree | 2026-04-26T16:18:49.676440+00:00 | feat-task2-benchmark-per-pr |
| fixture-heading | task2-implement-plan-event-trace-writer | 2026-04-27T05:33:53.552729+00:00 | task2-implement-loop-multi-tool-last-action |

## Never Passed

| Case | First seen | Total runs seen |
|---|---|---|
| correction-l1-miss-l2-hit | task2-implement-self-correction-proof | 13 |
| drift-submit-form-v1 | master | 22 |
| drift-submit-form-v2 | master | 22 |
| maintenance-drift-rename-v1 | task2-implement-self-correction-proof | 13 |
| maintenance-drift-rename-v2 | task2-implement-self-correction-proof | 13 |

## Stable

| Case | Status |
|---|---|
| live-conditional-pick | always skipped |
| live-form-fill | always skipped |
| live-multi-page-nav | always skipped |
| live-read-summarize | always skipped |
| live-search-extract | always skipped |
