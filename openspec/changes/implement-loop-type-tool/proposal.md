## Why

With `click(intent)` now wired (#59), the next failure class is form-fill tasks. Any case that requires typing into an `<input>` or `<textarea>` before submitting is unreachable because there is no `type` tool in `TOOLS`. Once a "fill email then submit" benchmark case is added — or the `live-form-fill` gate is lifted — the agent will fail immediately after a successful click on the input field: it can position focus but cannot enter text. Adding `type(intent, text)` closes this gap.

## What Changes

- Add a `type(intent: str, text: str)` entry to `TOOLS` in `agent/loop.py` — the LLM can now ask the agent to fill a textbox.
- Add a `type` branch to `_dispatch` in `agent/loop.py`: resolve the target element via `_locate_with_supervisor` (same ladder and cache path as `read` and `click`), call `Locator.fill(text)` on the resolved Playwright Locator, detect the fill outcome, and emit an `ActEvent` with `outcome ∈ {ok, timeout, error}`.
- On `LocatorMiss(reason="zero_matches")` from L1, surface to the supervisor for L1→L2 escalation (same path as `read` and `click`). For textbox-role intents, `locate_l2` already falls back to `get_by_placeholder`, so L2 escalation can succeed where L1 misses on placeholder-only inputs.
- On retry exhaustion or non-textbox intent, return an error string the model can recover from (do NOT terminate the run).
- Update `ToolName` literal in `loop.py` to include `"type"`.

## Capabilities

### New Capabilities

*(none — `type` is an extension of the existing loop tool surface, not a new standalone capability)*

### Modified Capabilities

- `agent-loop`: the `LLM tool surface exposed by the loop` requirement currently lists `goto`, `read`, `click`, `done`, `fail` and explicitly prohibits `type`; it must be updated to add `type(intent: str, text: str)` and to remove `type` from the prohibition clause.

## Impact

- `task2/agent/loop.py` — `TOOLS` list, `ToolName` literal, `_dispatch` function.
- `task2/tests/` — new fixture page for type-to-value, LocatorMiss→error test.
- No changes to `agent/locate.py`, `agent/supervisor.py`, or `agent/trace.py` — `ActEvent.tool` is already `str` (accepts `"type"` without schema widening), `locate_l2` already handles `role="textbox"` via `get_by_placeholder`, and the supervisor L1→L2 wiring is already in `_locate_with_supervisor`.
