## Why

The agent loop (`loop.py`) and supervisor (`supervisor.py`) were wired up in tickets #8 and #9, but the end-to-end escalation path — L1 fails → supervisor classifies → loop retries via L2 — has never been exercised under test. Ticket #10 closes this gap: a test fixture where L1 is guaranteed to fail by design forces the loop to traverse the L1 → L2 escalation path, proving that self-correction actually works at the loop level (not just in the supervisor or locator in isolation).

## What Changes

- Add a new HTML fixture `task2/tests/fixtures/loop_self_correction.html` — a page with a submit control that has **no accessible name** (the `<button>` element has no text content, no `aria-label`, and no linked `<label>`), so L1's `get_by_role("button", name="Submit")` returns zero matches. The element is discoverable by L2's text-contains heuristic once the button's visible text is revealed via a workaround, OR it is a `<button>` inside a `<form>` whose surrounding text allows L2 to match it. The exact HTML design is settled in design.md; the requirement is that L1 fails deterministically and L2 succeeds.
- Extend `task2/tests/agent/test_loop.py` with a new test `test_loop_self_correction` that:
  - Navigates to the new fixture.
  - Issues a `read` tool call with `intent="Submit button"`.
  - Verifies the run returns `status="succeeded"` after L1 fails and L2 resolves.
  - The test will fail if the supervisor escalation path in the loop is broken (i.e., if `LocatorMiss` from L1 is not caught and escalated).
- Wire the supervisor escalation path into `loop.py`'s `read` dispatch: when `locate()` raises `LocatorMiss` with `reason="zero_matches"`, the loop must invoke `Supervisor.handle()`, receive `next_tier="L2_dom"`, retry via `locate_l2()`, and continue. Without this wiring, the test fails; with it, the test passes.
- No changes to `agent/locate.py`, `agent/supervisor.py`, `agent/browser.py`, `agent/llm.py`, or `agent/locator_cache.py`.

## Capabilities

### New Capabilities

(none — this change adds a test scenario but no new spec-level capability)

### Modified Capabilities

- `agent-loop`: The loop's `read` dispatch must catch `LocatorMiss(reason="zero_matches")` from `locate()`, escalate via `Supervisor`, and retry at the next tier. This is a new requirement on the loop's recovery behavior that was explicitly deferred from ticket #9.

## Impact

- **Code**: modified `task2/agent/loop.py` (add supervisor escalation in `read` dispatch); new `task2/tests/fixtures/loop_self_correction.html`; `task2/tests/agent/test_loop.py` extended with one new test function.
- **Dependencies**: none new. `Supervisor` is already implemented in `agent/supervisor.py`.
- **Existing modules**: `agent/locate.py`, `agent/supervisor.py`, `agent/browser.py`, `agent/llm.py`, `agent/locator_cache.py` unchanged.
- **Spec**: `openspec/specs/agent-loop/spec.md` gains a delta section covering the self-correction requirement.
