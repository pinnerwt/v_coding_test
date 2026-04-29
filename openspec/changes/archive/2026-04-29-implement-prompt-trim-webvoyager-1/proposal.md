## Why

webvoyager-1 exits `reason="seconds_budget"` at step 13 with 127s wall-clock because prompt tokens accumulate 20x over 13 steps (1,084 → 21,522), driving ~105s of LLM time total; trimming stale tool-result messages from conversation history reduces per-step prompt tokens by ~30%, saving ~31s and bringing the run to ~96s — comfortably under the 120s budget.

## What Changes

- Add a `trim_history` function to `task2/agent/loop.py` (or an adjacent `task2/agent/history.py` module) that accepts the full `messages` list and a `keep_steps` window and drops tool-result messages (role `"tool"`) and their paired assistant tool-call messages that are older than the configured window.
- Wire `trim_history` into the per-step conversation-building path in `loop()`, applied after `_compact_messages` so the two compaction strategies compose correctly.
- Expose `HISTORY_TRIM_KEEP_STEPS` as an environment-variable-configurable parameter (default: `4`) so the Zeabur deployment can tune it without a code change.

## Capabilities

### New Capabilities

<!-- None — the trim is a bounded extension of an existing capability. -->

### Modified Capabilities

- `agent-loop`: Add a new requirement for conversation-history trimming that drops stale tool-result messages outside a configurable step window.

## Impact

- `task2/agent/loop.py` — trim function added, wired into the per-step message construction.
- `task2/tests/` — new unit test `test_trim_history.py` (no LLM, no network).
- Environment variable `HISTORY_TRIM_KEEP_STEPS` (int, default 4) added to the configurable surface.
- No change to the public `loop()` signature; trim is applied internally.
