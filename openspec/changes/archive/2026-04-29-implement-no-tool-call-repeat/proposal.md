## Why

`webvoyager-1` ("List the latest version of Python") timed out at `steps=20, $0.2978, 281.6s` even after PR #104 / ticket #70 shipped `_stuck_buf` — because every step emitted a text-only response with no tool calls, so the K=3 identical-tool-call buffer never accumulated any entries to compare. The no-tool-call shape is a second distinct "stuck planner" failure mode that the existing `stuck_repeat` path cannot catch, and it has appeared in two consecutive benchmark runs costing ~$0.30 + 280s each with zero useful signal.

## What Changes

- Add module-level constant `_NO_TOOL_CALL_K = 3` in `agent/loop.py`.
- Add counter `_consecutive_no_tool_call_steps` initialized to `0` at the start of `loop()`.
- Each step where the LLM response yields no tool calls AND `step_num > 0` (excluding the plan step at step 0): increment the counter.
- Each step where at least one tool call is produced: reset the counter to `0`.
- When counter reaches `_NO_TOOL_CALL_K`: call `_record_step(...)` and return `RunResult(status="failed", reason="no_tool_call_repeat", ...)` with the same metric-field discipline as the `stuck_repeat` exit.
- Extend `RunResultReason` from `Literal["stuck_repeat"]` to `Literal["stuck_repeat", "no_tool_call_repeat"]`.
- Add two unit tests: one asserting `status="failed"` + `reason="no_tool_call_repeat"` + `steps==3` for K=3 consecutive no-tool-call responses; one control asserting counter resets when a tool call fires between no-tool-call steps.

## Capabilities

### New Capabilities

<!-- None: no new spec file needed; this is a delta on the existing agent-loop capability. -->

### Modified Capabilities

- `agent-loop`: Two requirement changes — (1) `RunResultReason` extended from `Literal["stuck_repeat"]` to include `"no_tool_call_repeat"`; (2) new early-termination rule when the LLM emits K consecutive responses with no tool calls.

## Impact

- `task2/agent/loop.py`: counter + constant + early-return path added.
- `task2/tests/` (test file for loop): two new test cases.
- `openspec/specs/agent-loop/spec.md`: two requirement changes (MODIFIED + ADDED).
- No external API, dependency, or schema changes.
