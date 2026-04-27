## Why

When an LLM response carries N>1 tool calls in one reply, the loop assigns `last_action` once per call and overwrites it each time, so only the final call's action survives into the next observation; the earlier N-1 actions are silently lost from the model's context window. This prevents the model from reasoning about everything it just did and creates hidden state bugs.

## What Changes

- Replace the single `last_action: dict | None` variable in `loop.py` with `last_actions: list[dict]` — an ordered list of every action dispatched since the previous observation.
- After all tool calls in a step are dispatched, pass `last_actions` (the full list) into `observe.build_observation`.
- Change `observe.build_observation` signature to accept `last_actions: list[dict]` and emit a `last_actions` key (list) in the observation dict instead of `last_action` (single dict).
- Update `ObservationEvent` in `trace.py` to carry `last_actions: list[dict]` instead of (or in addition to) `last_action`.
- Keep backward-compat: existing callers that only supply a single action still produce a length-1 list, not a regression.

## Capabilities

### New Capabilities

- None — this is purely a modification of existing capability behavior.

### Modified Capabilities

- `agent-loop`: Requirement "loop observation uses AX-tree digest" extends to `last_actions` list threading (replaces single `last_action`); new scenario: multi-tool-call step produces `last_actions` with all dispatched actions in order.
- `trace-schema-writer`: `ObservationEvent` shape changes — `last_action: dict | None` field replaced by `last_actions: list[dict]`.

## Impact

- **`task2/agent/loop.py`** — `last_action` variable replaced by `last_actions` list; threaded into `build_observation` each step.
- **`task2/agent/observe.py`** — `build_observation` signature changes; emitted dict key changes from `last_action` to `last_actions`.
- **`task2/agent/trace.py`** — `ObservationEvent` field change.
- **`task2/tests/agent/test_loop.py`** — existing assertions on `last_action` key in observation JSON must be migrated to `last_actions`; new multi-tool test added.
- **`task2/tests/agent/test_observe.py`** — update fixture/assertion for new key.
- **`task2/tests/agent/test_trace.py`** — update `ObservationEvent` construction and round-trip test.
