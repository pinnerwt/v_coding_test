## Context

webvoyager-2's step_breakdown from `task2/benchmark/task2-implement-prompt-trim-webvoyager-1/webvoyager/20260429_220514.json`:

- Step 1 `goto` → establishes the search page (group index 0 in trim_history)
- Step 2 `type` → sets the query
- Step 3 `click` → submits
- Step 4 `click` → selects a result
- Steps 5–8 `type`, `type`, `type`, `type` → repeated form-fill, no progress; `no_progress` fires at step 8

At step 5, `trim_history(messages, keep_steps=4)` drops `groups[0 : 6 - 4]` = `groups[0:2]`, which includes the step-1 `goto` + its observation (group 0) and the step-2 `type` + its result (group 1). Losing group 0 means the planner no longer sees the original landing page context; it re-issues `type` actions against whatever partial state remains.

## Fix: Anchor-Preservation (chosen)

Change the drop slice from `groups[: len(groups) - keep_steps]` to `groups[1 : len(groups) - keep_steps]`.

Before:
```
drop_groups = groups[: len(groups) - keep_steps]
```

After:
```
drop_groups = groups[1 : len(groups) - keep_steps]
```

This makes group index 0 unconditionally retained. The most recent `keep_steps` groups are still retained. Everything between groups[1] and groups[N-keep_steps] is eligible for removal. For a 6-group history with keep_steps=4, only groups[1:2] = group 1 is dropped; groups 0, 2, 3, 4, 5 are kept. For keep_steps=2, groups[1:4] = groups 1, 2, 3 are dropped; groups 0, 4, 5 are kept.

Edge case — `len(groups) == keep_steps + 1`: drop slice is `groups[1:1]` which is empty; no group is dropped. Correct — the anchor is not needed when the window is large enough to include everything except one group; the existing `len(groups) <= keep_steps` guard already handles `len(groups) == keep_steps`.

Edge case — `len(groups) == 1`: the single group is the anchor; `len(groups) <= keep_steps` guard returns early, no drop attempted.

## Alternative: Raise Default keep_steps (not chosen)

Raise `HISTORY_TRIM_KEEP_STEPS` from 4 to 6 or 8. Trade-off: webvoyager-1's prompt-token growth returns (prompt_tokens accumulates to 21,522 by step 13), which may re-trip the `seconds_budget` exit. The anchor-preservation fix has smaller blast radius: it drops exactly one fewer group than before on typical 6-group histories, and the token savings are largely preserved because it is only the first group (small, typically just a `goto` + short observation) that is spared.

## Test Impact

The following tests in `task2/tests/test_trim_history.py` require assertion updates (old contract assumed group 0 was droppable):

- `test_trim_history_drops_oldest_groups_outside_window` — 6 groups, keep_steps=4. Old: kept={tc-3..tc-6}, dropped={tc-1,tc-2}. New: kept={tc-1,tc-3,tc-4,tc-5,tc-6}, dropped={tc-2} only.
- `test_trim_history_respects_env_var` — HISTORY_TRIM_KEEP_STEPS=2, 6 groups. Old: kept={tc-5,tc-6}, dropped={tc-1..tc-4}. New: kept={tc-1,tc-5,tc-6}, dropped={tc-2,tc-3,tc-4}.
- `test_trim_history_unparseable_env_var_falls_back_to_default` — default keep_steps=4, 6 groups. Old: kept={tc-3..tc-6}, dropped={tc-1,tc-2}. New: kept={tc-1,tc-3,tc-4,tc-5,tc-6}, dropped={tc-2}.
- `test_trim_history_drops_multi_tool_call_group_atomically` — currently 2 groups, keep_steps=1. With anchor-preservation and only 2 groups, drop slice is `groups[1:1]` = empty; no group is dropped. The test intent (verify atomic drop of a multi-tool-call group) is no longer exercised. Fix: rebuild this test with 3 groups — a single-tool-call anchor (group 0), a multi-tool-call middle group (group 1), and a single-tool-call recent group (group 2) — then call keep_steps=1. The drop slice becomes `groups[1:2]` = group 1 only; assert that both tc-multi-a and tc-multi-b are absent while tc-anchor and tc-keep remain.

New test added:
- `test_trim_history_preserves_first_tool_group_when_window_smaller` — 6 groups, keep_steps=2. Assert tc-1 is present in the output (in addition to tc-5 and tc-6). This test fails red against the current implementation and goes green after the one-line fix.

## Risks / Trade-offs

- The anchor (group 0) is always small (typically a single `goto` + short page-body observation), so the token cost of never dropping it is low.
- On very long tasks (>10 steps) with a tiny keep_steps, the history will contain group 0 plus the most recent keep_steps groups and nothing in between; this is the intended contract.
- The `no_progress` false-positive risk is eliminated for 8+ step tasks that start with a `goto` whose result is load-bearing. Tasks that begin with a different tool call (e.g. `read`) are also protected since they use group 0 by definition.
