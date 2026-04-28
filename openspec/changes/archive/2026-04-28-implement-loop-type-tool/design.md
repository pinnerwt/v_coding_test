## Context

`agent/loop.py` now exposes five tools to the LLM: `goto`, `read`, `click`, `done`, `fail`. The `click` branch in `_dispatch` (added by #59) calls `_locate_with_supervisor` → `Locator.click(timeout=5000)` → `_emit_act_event`. The `type` branch follows the identical plumbing: `_locate_with_supervisor` → `Locator.fill(text)` → `_emit_act_event`. The locator ladder already handles `role="textbox"` at L2 via `locate_l2` using `page.get_by_placeholder(name, exact=False)` (see `locate.py` line 175-178). `ActEvent.tool` is typed as `str` in `trace.py` — no schema change is needed. Nothing in `agent/locate.py`, `agent/supervisor.py`, or `agent/trace.py` needs to change.

## Goals / Non-Goals

**Goals:**
- Add `type(intent: str, text: str)` to `TOOLS` so the LLM can fill textboxes.
- Dispatch through the existing `_locate_with_supervisor` path (same as `read` and `click`).
- Emit `ActEvent` with the correct outcome (`ok`, `timeout`, `error`) after each fill.
- Surface `LocatorMiss(zero_matches)` from L1 to the supervisor for L1→L2 escalation; for textbox-role intents `locate_l2` falls back to `get_by_placeholder`, enabling escalation to succeed where L1 misses on non-ARIA inputs.
- On retry exhaustion, return an error string and continue the loop (no crash, no forced `fail`).

**Non-Goals:**
- Adding `select`, `wait_for`, `back`, `screenshot`, or `clear` — those are separate tickets.
- Changing `agent/locate.py`, `agent/supervisor.py`, or `agent/trace.py`.
- Implementing a `LocatorMiss`-on-non-textbox-role guard in the `type` branch — the locate ladder already raises `LocatorMiss` for non-matching role/name combos; the error is surfaced to the LLM as a recoverable tool error.
- Validating that the resolved element is actually a textbox before calling `fill` — Playwright will raise a `playwright.sync_api.Error` if the element is not fillable, which maps to `outcome="error"` and is returned as a recoverable error string.

## Decisions

**Decision: reuse `_locate_with_supervisor` unchanged.**

`click` already calls `_locate_with_supervisor(page, intent, supervisor, cache=…, trace_writer=…, run_id=…, step_id=…)`. The `type` branch will call the same helper with the same arguments. No new locate-path code needed.

**Decision: use `Locator.fill(text)` rather than `Locator.type(text)`.**

`Locator.fill` is the Playwright idiom for setting the full value of an input in one operation. `Locator.type` simulates key-by-key typing (useful for key-event listeners) but is slower and not needed for generic form fill. `fill` is the minimal correct action.

**Decision: catch `playwright.sync_api.TimeoutError` → `outcome="timeout"`, all other `playwright.sync_api.Error` → `outcome="error"`.**

Mirrors the `click` branch exactly. The outcome string is returned to the LLM so it can replan. The loop is NOT terminated.

**Decision: `ActEvent.diff = {}`.**

Screenshot-diff is deferred to a future ticket. An empty dict is a valid value per the existing schema.

**Decision: update `ToolName` literal.**

`ToolName = Literal["goto", "read", "click", "type", "done", "fail"]`. Keeps the type annotation accurate without changing any runtime branching logic.

**Decision: no `_dispatch_type` helper — inline the branch.**

The `click` branch is already inlined in `_dispatch` (no `_dispatch_click` helper was extracted). The `type` branch will follow the same pattern for consistency.

## Risks / Trade-offs

- **Risk: `Locator.fill` raises `playwright.sync_api.Error` for elements that are not editable (e.g. a `<div contenteditable>` resolved at L2).** → Mitigation: the error is caught and mapped to `outcome="error"`; the LLM receives an error string and can replan. No crash.
- **Risk: `locate_l2` for textbox uses `get_by_placeholder`, which matches on the `placeholder` attribute only.** If the textbox has no placeholder and no ARIA role, both L1 and L2 will miss, and the supervisor will halt. → Mitigation: the loop returns an error string for the LLM to replan. This is the intended graceful-degradation path.
- **Risk: `ActEvent.diff={}` is semantically incomplete.** → Mitigation: explicitly deferred to the screenshot-diff ticket; empty dict is valid per the schema.

## Open Questions

*(none — all decisions above are deterministic given the existing codebase constraints)*
