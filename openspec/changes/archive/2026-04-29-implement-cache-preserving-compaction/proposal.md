## Why

Two consecutive WebVoyager runs (`task2-fix-goto-domcontentloaded/webvoyager/20260429_122531.json` and `task2-implement-fast-path-ticket-archival/webvoyager/20260429_104152.json`) show the same per-step latency cliff on `webvoyager-1`: steps 1-12 run at ~5-12s/step, steps 13-20 jump to ~28-31s/step (4× slowdown), and the case ends in `status=timeout` at the 20-step ceiling having burned 322-373s of wall-clock and ~340k prompt tokens. The cliff aligns with `_compact_messages` (`agent/loop.py:174`) firing for the first time around step 12-13. Today's compactor *rewrites* mid-conversation message content in place (`_ELIDED_STATE_CONTENT`, `_ELIDED_TOOL_CONTENT`), which mutates the prefix the LLM server has already KV-cached. On the local Qwen 27B endpoint this forces a full ~22k-token re-prefill on every subsequent step — exactly the ~22s overhead observed.

## What Changes

- Rewrite `_compact_messages` in `agent/loop.py` to **drop oldest non-system messages** instead of in-place `<elided>` substitution. The kept tail SHALL be byte-identical to the prior step's prefix so the LLM server's prefix cache survives across steps.
- The compactor SHALL preserve the system message (index 0) and SHALL keep the most recent state message (since `last_state_idx` is what the planner conditions on for the upcoming decision).
- Drop oldest messages contiguously (after the system message, before the kept tail). This keeps the kept-tail invariant: index `i` of the new list, for `i >= 1`, is byte-identical to some index `j > i` of the prior call's input.
- Remove `_ELIDED_STATE_CONTENT` and `_ELIDED_TOOL_CONTENT` constants — they are no longer used.
- **BREAKING (internal-only)**: existing tests asserting the presence of `<elided>` content in compacted messages will need to be removed or rewritten to assert byte-identity of the kept tail.

## Capabilities

### New Capabilities

- (none)

### Modified Capabilities

- `agent-loop`: the contract for `_compact_messages` changes from "rewrite oldest mid-conversation contents to elision sentinels until total fits budget" to "drop oldest non-system messages until total fits budget; kept messages SHALL be byte-identical to inputs."

## Impact

- `task2/agent/loop.py` — rewrite `_compact_messages`, drop `_ELIDED_STATE_CONTENT` / `_ELIDED_TOOL_CONTENT` constants.
- `task2/tests/agent/test_loop.py` (or a dedicated `test_compact_messages.py`) — new unit tests covering: (1) byte-identity of kept tail, (2) prefix-stability across consecutive compactions, (3) system message preserved, (4) most-recent state preserved.
- No public API change; `loop()` signature unchanged. The only externally observable effect is reduced per-step latency / token cost on long-running cases that hit the budget.
