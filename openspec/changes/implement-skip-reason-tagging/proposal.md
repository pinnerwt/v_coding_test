## Why

Every skipped `CaseResult` today carries `status="skipped"` but no information about *why* it was skipped, making it impossible to distinguish live-disabled cases from fixture-missing or infra-unavailable ones in the scoreboard or CI logs. Ticket #34 requires tagging each skip with a machine-readable reason so the scoreboard can surface actionable skip breakdowns.

## What Changes

- Add `skip_reason: Literal["live_disabled", "infra_unavailable", "fixture_missing", "feature_not_implemented"] | None` to `CaseResult`; default `None` for non-skipped cases.
- Require `skip_reason` to be non-`None` whenever `status="skipped"`; enforce at construction time (raise `ValueError` on unknown reason value).
- Wire `_skipped_result()` in `eval.py` to set `skip_reason="live_disabled"` for the `not live and not fixture` skip path.
- Wire `load_cases()` to raise a `ValueError` with a `fixture_missing` signal when a referenced fixture file does not exist, and set `skip_reason="fixture_missing"` in the resulting `CaseResult` when a case is skipped due to a missing fixture.
- Surface a **"Skipped" subsection** in the scoreboard below the per-case table: lists each `skip_reason` value and the count of cases with that reason.

## Capabilities

### New Capabilities

*(none — both surfaces are extensions of existing capabilities)*

### Modified Capabilities

- `eval-runner`: `CaseResult.skip_reason` field; validation at construction; `_skipped_result()` wired to `"live_disabled"` and `"fixture_missing"` skip paths.
- `score-script`: New "Skipped" subsection with reason counts appended after the per-case table and before mechanism firing rates.

## Impact

- `task2/scripts/eval.py`: `CaseResult` dataclass, `_skipped_result()` function, `run_suite()` skip branch.
- `task2/scripts/score.py`: `generate_scoreboard()` — new "Skipped" subsection block.
- `task2/tests/test_eval.py`: new tests for skip-reason tagging and rejection of unknown reasons.
- `task2/tests/test_score.py`: new tests for "Skipped" subsection rendering.
- Results JSON: `skip_reason` key added to each case entry (backwards-compatible — `null` for non-skipped).
