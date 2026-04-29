## Why

The agent loop's existing stuck-detection (`_stuck_buf`) only fires when the **same tool call with byte-identical args** is repeated `_STUCK_REPEAT_K=3` times. Real thrashing — as observed in `webvoyager-1` steps 13-20 — uses different tool names and varying args each step but makes zero forward progress because the AX-tree never changes and no `click`/`type` succeeds. The current guard cannot detect this pattern, leaving 4–8 "wasted" steps burning ~240 s and ~180 k prompt tokens per case before `timeout` fires.

## What Changes

- Add a **parallel** `_no_progress_buf` to `agent/loop.py` (list of the last `_NO_PROGRESS_K=4` `(ax_fingerprint, any_action_succeeded)` tuples). The buf is populated at the end of each step's dispatch, keyed on the post-dispatch AX fingerprint and whether any `click`/`type`/`goto`/`read` tool call's result did not start with `"Error:"` during that step (the wider set covers exploratory flows; see design Decision 3).
- When all 4 entries in the buffer share the same fingerprint AND all have `any_action_succeeded=False`, the loop returns early with `RunResult(status="failed", reason="no_progress")`, after emitting a normal step record (so latency breakdown and cost metrics are preserved).
- Extend `RunResultReason` Literal to include `"no_progress"` alongside the existing `"stuck_repeat"`, `"no_tool_call_repeat"`, and `"seconds_budget"` values.
- The existing `_stuck_buf` mechanism is **not changed**; both guards run in parallel, whichever fires first wins.

## Capabilities

### New Capabilities

- (none — this extends an existing spec capability)

### Modified Capabilities

- `agent-loop`: new early-termination requirement "Loop terminates early when N consecutive steps share an unchanged AX fingerprint and emit no successful action"; also extends the `RunResultReason` Literal with `"no_progress"`.

## Impact

- **Code**: `task2/agent/loop.py` — add `_NO_PROGRESS_K`, `_no_progress_buf`, fingerprint capture logic after dispatch, bail check, and extended `RunResultReason` Literal.
- **Tests**: `task2/tests/` — three new unit tests (positive: bail at step 4; negative: alternating fingerprint; negative: stuck fingerprint but `click` returned `ok`).
- **Specs**: `openspec/specs/agent-loop/spec.md` — delta applied from this change's `specs/agent-loop/spec.md`.
- No new external dependencies; AX fingerprint already computed by `observe.build_observation`.
