## Context

`agent/loop.py` exposes four tools to the LLM: `goto`, `read`, `done`, `fail`. The locator ladder (`_locate_via_ladder` / `_locate_with_supervisor`) and supervisor escalation are already wired for the `read` branch. `agent/trace.py` already defines `ActEvent` with `outcome: Literal["ok", "no_effect", "nav", "timeout", "error"]`. The `Supervisor` already handles `("L1_ax", "zero_matches") → "L2_dom"`. Nothing in `agent/locate.py`, `agent/supervisor.py`, or `agent/trace.py` needs to change.

Five benchmark cases — `correction-l1-miss-l2-hit`, `drift-submit-form-v1`, `drift-submit-form-v2`, `maintenance-drift-rename-v1`, `maintenance-drift-rename-v2` — all follow the same failure shape: the LLM reads the page, finds no path forward without clicking, and calls `fail`. All five become solvable once `click` is in `TOOLS`.

## Goals / Non-Goals

**Goals:**
- Add `click(intent: str)` to `TOOLS` so the LLM can click elements.
- Dispatch through the existing `_locate_with_supervisor` path (same as `read`).
- Emit `ActEvent` with the correct outcome after each click.
- Surface `LocatorMiss(zero_matches)` from L1 to the supervisor for L1→L2 escalation (same wiring as `read`).
- On retry exhaustion, return an error string and continue the loop (no crash, no forced `fail`).

**Non-Goals:**
- Adding `type`, `select`, `wait_for`, `back`, or `screenshot` — those are separate tickets.
- Changing `agent/locate.py`, `agent/supervisor.py`, or `agent/trace.py`.
- Post-click screenshot diffing or DOM-diff verification.
- Updating `Browser` — `Locator.click(timeout=…)` is called directly on the Playwright `Locator` returned by `_locate_with_supervisor` via `page.locator(result.selector)`.

## Decisions

**Decision: reuse `_locate_with_supervisor` unchanged.**

`read` already calls `_locate_with_supervisor(page, intent, supervisor, cache=…, trace_writer=…, run_id=…, step_id=…)` and the supervisor L1→L2 escalation fires from there. The `click` branch will call the same helper with the same arguments. No new locate-path code needed.

**Decision: detect navigation by comparing `page.url` before and after click.**

After a successful `Locator.click(timeout=…)`, compare `page.url` before and after. If different → `outcome="nav"`. If same → `outcome="ok"`. This is simpler and more reliable than listening to `page.on("framenavigated", …)` which requires async wiring.

**Decision: catch `playwright.sync_api.TimeoutError` → `outcome="timeout"`, all other `PlaywrightError` → `outcome="error"`.**

The `ActEvent` literal already covers both. The error string is returned to the LLM as the tool result so it can replan. The loop is NOT terminated.

**Decision: emit `ActEvent` via a new `_emit_act_event` helper in `loop.py`.**

Mirrors the existing `_emit_locate_event` / `_emit_supervisor_event` pattern. Keeps `_dispatch` readable. `ActEvent.diff` is set to `{}` for now (screenshot-diff is a future ticket).

**Decision: update `ToolName` literal.**

`ToolName = Literal["goto", "read", "click", "done", "fail"]`. Keeps the type annotation accurate without changing any runtime branching logic.

## Risks / Trade-offs

- **Risk: click causes page navigation but `page.url` comparison races with Playwright's async navigation event.** → Mitigation: use `page.wait_for_load_state("load")` with a short timeout after click before comparing URLs; mark `outcome="nav"` if URL changed.
- **Risk: L2-resolved selector matches the wrong element after DOM mutation from a prior click.** → Mitigation: the cache fingerprint check on subsequent locate calls already handles this; no extra work needed here.
- **Risk: `ActEvent.diff={}` is semantically wrong (no diff computed).** → Mitigation: this is explicitly deferred to the screenshot-diff ticket; an empty dict is a valid value per the schema.

## Open Questions

*(none — all decisions above are deterministic given the existing codebase constraints)*
