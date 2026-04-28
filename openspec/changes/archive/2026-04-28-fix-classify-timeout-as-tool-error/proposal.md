## Why

`_classify_failure` in `scripts/eval.py` only catches `ActEvent(outcome="error")` as `tool_error`, but `ActEvent.outcome` can also be `"timeout"` (Playwright `wait_for` exhausted). A failed run whose only signal is a browser timeout silently falls through to `no_done_emitted`, losing the more specific signal. This means scoreboard failure-class data is inaccurate for timeout-driven failures.

## What Changes

- Widen the `_classify_failure` predicate at line 201 of `scripts/eval.py` from `ev.outcome == "error"` to `ev.outcome in ("error", "timeout")` so both outcomes map to the existing `"tool_error"` literal.
- Add a new test in `task2/tests/test_eval.py`: synthetic `ActEvent(outcome="timeout")` with `status="failed"` must classify as `("tool_error", <non-empty string>)`.
- Update spec rule 2.c in `openspec/specs/failure-classification/spec.md` (via a delta) to reflect the widened predicate.

## Capabilities

### New Capabilities

*(none)*

### Modified Capabilities

- `failure-classification`: Rule 2.c widens the `tool_error` predicate to cover `outcome in {"error", "timeout"}`; new scenario added for the `timeout` case.

## Impact

- `task2/scripts/eval.py` — one-line predicate change inside `_classify_failure`.
- `task2/tests/test_eval.py` — one new test function mirroring the existing `test_classify_failure_tool_error`.
- `openspec/specs/failure-classification/spec.md` — requirement text and scenario updated via delta spec.
- No API surface changes; `failure_class` literal set is unchanged (`"tool_error"` already exists).
