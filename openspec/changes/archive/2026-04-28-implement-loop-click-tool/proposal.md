## Why

Every benchmark case whose task starts with "Click the … button" — `correction-l1-miss-l2-hit`, `drift-submit-form-v1/v2`, `maintenance-drift-rename-v1/v2` — fails today because the agent tool surface has no `click` tool: the LLM reads the page once, finds nothing actionable, and voluntarily calls `fail`. Adding `click(intent)` is the single change projected to flip 5 red benchmark cases to green (44% → ~89% pass rate).

## What Changes

- Add a `click(intent: str)` entry to `TOOLS` in `agent/loop.py` — the LLM can now ask the agent to click a resolved element.
- Add a `click` branch to `_dispatch` in `agent/loop.py`: resolve via `_locate_with_supervisor` (already wired for `read`), call `Locator.click(timeout=…)`, detect navigation outcome via `Page.url` comparison, and emit an `ActEvent` with `outcome ∈ {ok, no_effect, nav, timeout, error}`.
- On `LocatorMiss(reason="zero_matches")` from L1, surface to the supervisor for L1→L2 escalation (same path as `read` currently fires 3/9 escalations).
- On retry exhaustion, return an error string and continue (do NOT terminate the loop).
- Update `ToolName` literal in `loop.py` to include `"click"`.

## Capabilities

### New Capabilities

*(none — `click` is an extension of the existing loop tool surface, not a new standalone capability)*

### Modified Capabilities

- `agent-loop`: the `LLM tool surface exposed by the loop` requirement currently prohibits `click`; it must be updated to add `click(intent: str)` to the exposed tools list and specify the dispatch contract (locate → Locator.click → ActEvent → supervisor on miss).

## Impact

- `task2/agent/loop.py` — `TOOLS` list, `ToolName` literal, `_dispatch` function.
- `task2/tests/` — new fixture-page test for click-to-done, outcome=nav test, LocatorMiss→SupervisorEvent test.
- No changes to `agent/locate.py`, `agent/supervisor.py`, `agent/trace.py` — the existing ActEvent schema and supervisor wiring are already sufficient.
