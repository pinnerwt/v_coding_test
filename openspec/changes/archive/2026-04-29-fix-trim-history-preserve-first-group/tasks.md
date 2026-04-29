## 1. Red — Failing Unit Test

- [x] 1.1 In `task2/tests/test_trim_history.py`, add `test_trim_history_preserves_first_tool_group_when_window_smaller`. Build a messages list using `_build_messages()` (6 groups, tc-1 through tc-6). Call `trim_history(messages, keep_steps=2)`. Assert that `tc-1` is present in both the assistant tool_calls and the tool result_ids of the returned list (in addition to tc-5 and tc-6). Do not change any existing test in this commit.
- [x] 1.2 Run `uv run pytest task2/tests/test_trim_history.py::test_trim_history_preserves_first_tool_group_when_window_smaller -x` from `task2/` and confirm it fails (AssertionError: tc-1 is absent). Record the failure line.

## 2. Green — Minimal Fix

- [x] 2.1 In `task2/agent/loop.py`, in the `trim_history` function, change the drop-group slice from `groups[: len(groups) - keep_steps]` to `groups[1 : len(groups) - keep_steps]`. No other production code changes.
- [x] 2.2 Run `uv run pytest task2/tests/test_trim_history.py::test_trim_history_preserves_first_tool_group_when_window_smaller -x` and confirm it passes.

## 3. Update Existing Tests to New Contract

- [x] 3.1 Update `test_trim_history_drops_oldest_groups_outside_window` (keep_steps=4, 6 groups): change `kept_ids` to `{tc-1, tc-3, tc-4, tc-5, tc-6}` and `dropped_ids` to `{tc-2}`.
- [x] 3.2 Update `test_trim_history_respects_env_var` (HISTORY_TRIM_KEEP_STEPS=2, 6 groups): change `kept_ids` to `{tc-1, tc-5, tc-6}` and `dropped_ids` to `{tc-2, tc-3, tc-4}`.
- [x] 3.3 Update `test_trim_history_unparseable_env_var_falls_back_to_default` (default keep_steps=4, 6 groups): change `kept_ids` to `{tc-1, tc-3, tc-4, tc-5, tc-6}` and `dropped_ids` to `{tc-2}`.
- [x] 3.4 Rebuild `test_trim_history_drops_multi_tool_call_group_atomically` with 3 groups instead of 2. Use a single-tool-call anchor group (group 0, id=`tc-anchor`), a multi-tool-call middle group (group 1, ids=`tc-multi-a` and `tc-multi-b`), and a single-tool-call recent group (group 2, id=`tc-keep`). Call `trim_history(messages, keep_steps=1)`. Assert: `tc-multi-a` and `tc-multi-b` are absent from both tool result ids and assistant tool_call ids; `tc-anchor` and `tc-keep` are present. This preserves the original test intent (atomic drop of a multi-tool-call group) while accommodating the new anchor contract.
- [x] 3.5 Run `uv run pytest task2/tests/test_trim_history.py -x` and confirm all tests pass.

## 4. Refactor Under Green

- [x] 4.1 Run `uv run pytest task2/` to confirm the full test suite passes (no regressions in other test files).
- [x] 4.2 Run `uv run ruff check task2/agent/loop.py task2/tests/test_trim_history.py` and fix any lint issues.
- [x] 4.3 Run `uv run ruff format task2/agent/loop.py task2/tests/test_trim_history.py` and confirm no changes are needed (or apply and re-check).

## 5. Post-Implementation Benchmark Verification (manual gate, post-merge in /done_pr)

- [ ] 5.1 Run the webvoyager benchmark (all 3 cases) against the live Qwen endpoint three times independently. Confirm webvoyager-2 passes in at least 2 of 3 runs (recovering the PR #154 regression: pass_rate 1/3 → ≥2/3).
- [ ] 5.2 Confirm webvoyager-1 does NOT regress on `steps` (must remain ≤10) or `latency_ms_total` (must remain ≤120,828 ms, the PR #154 baseline) in the same runs.
- [ ] 5.3 Record the benchmark run identifier in the ticket's `evidence` field before closing.
