## Why

`trim_history(messages, keep_steps=4)` introduced in PR #154 drops tool-result groups strictly from the oldest end of the list, with no concept of a "load-bearing anchor." For webvoyager-2 (8-step task), the initial `goto` + page-establishing observation (group index 0) falls outside the keep_steps=4 window once the conversation reaches step 5. With that anchor gone, the planner loses the original search intent and page-state context, producing 4 consecutive `type` calls (steps 5–8) on the same form field — the `no_progress` detector fires at step 8 and the run fails. The aggregate regression across PR #154: pass_rate 2/3 → 1/3, while the token win (-29.4%) is real and must be preserved.

## What Changes

- Modify `trim_history` in `task2/agent/loop.py` so that group index 0 (the chronologically first tool-result group) is always kept, regardless of the keep window. Only groups in `groups[1 : len(groups) - keep_steps]` are eligible for removal.
- Update four existing tests in `task2/tests/test_trim_history.py` whose assertions assumed the old contract (first group was droppable), and add one new red test that captures the anchor-preservation requirement before the fix.
- Extend `openspec/specs/agent-loop/spec.md` with the anchor-preservation bullet and a new scenario.

## Capabilities

### MODIFIED Capabilities

- `agent-loop`: The existing `Conversation-history trimming` requirement gains an anchor-preservation clause. No new capability is introduced; this is a correctness fix to the existing trimming contract.

## Impact

- `task2/agent/loop.py` — one-line change inside `trim_history`; no signature change.
- `task2/tests/test_trim_history.py` — one new test added (red→green); four existing tests updated to reflect the new contract.
- `openspec/specs/agent-loop/spec.md` — `Conversation-history trimming` requirement modified (via delta spec in this change).
- No change to `loop()` call site, no new env vars, no dependency changes.
