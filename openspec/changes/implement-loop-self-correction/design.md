## Context

Tickets #8 (supervisor) and #9 (loop happy path) are complete. The supervisor classifies `LocatorMiss` exceptions and returns an `EscalationDecision`; the loop drives observe → decide → act cycles and handles tool dispatch. However, `loop.py`'s `_dispatch` function passes `locate()` calls through without any error handling — a `LocatorMiss` raised inside the `read` tool handler propagates uncaught and would crash the loop with an unhandled exception rather than triggering self-correction.

The current `_resolve_via_ladder` in `locate.py` already tries L1 → L2 → L4 internally (for zero_matches) and L1 → L3 → L4 (for ambiguous). However, this internal ladder is not the "supervisor escalation path" described in the plan: the supervisor is supposed to sit *outside* the locator, at the loop level, so the loop can decide whether to retry, report the failure, or abandon. The test for ticket #10 must exercise the loop's ability to recover from a `LocatorMiss` that escapes `locate()`, not the locator's internal ladder.

The key insight: to force L1 to fail while L2 succeeds, the fixture must have a button with no accessible name at all. `get_by_role("button", name="Submit")` returns zero matches because there is no button with accessible name "Submit". L2's `filter(has_text="Submit")` succeeds because the button element has the visible text "Submit" but it is set via CSS `content` or a `data-*` attribute that bypasses the accessibility tree, OR (simpler) because the button's accessible name is deliberately blank/empty while its `textContent` is present — which is actually impossible with a plain `<button>Submit</button>` since `textContent` feeds both. The cleanest approach: use `aria-label=""` (empty string) to suppress the accessible name while keeping visible text.

**Actually the cleanest approach** for the fixture: `<button aria-label=" ">Submit</button>` — `aria-label` of a single space normalises to empty string in some browsers but visible text is "Submit". An even simpler approach that is guaranteed to work: use `role="button"` on a `<div>` with no accessible name computation path — but the L2 taxonomy CSS includes `[role=button]`. The most reliable fixture design is a `<button>` where `aria-label` overrides to something misleading (e.g. `aria-label="action"`), so L1's `get_by_role("button", name="Submit")` returns zero matches while L2's `filter(has_text="Submit")` still finds it (since `filter(has_text=...)` matches on visible text, not accessible name). This is the chosen design.

## Goals / Non-Goals

**Goals:**

- A new HTML fixture that guarantees `locate_l1(page, role="button", name="Submit")` raises `LocatorMiss(reason="zero_matches")`.
- The same fixture has exactly one button whose visible text contains "Submit", so `locate_l2` succeeds.
- `loop.py`'s `read` dispatch catches `LocatorMiss` and invokes `Supervisor.handle()` to get an escalation decision, then retries at the prescribed tier.
- A new test in `test_loop.py` that fails if the escalation wiring is missing and passes once it is present.

**Non-Goals:**

- L2 → L3 or L3 → L4 escalation in the loop (deferred to later tickets).
- Changes to `locate.py`, `supervisor.py`, `browser.py`, `llm.py`, or `locator_cache.py`.
- Modifying the existing happy-path or other tests.
- Wiring supervisor into the `goto` tool dispatch (only `read` with intent uses `locate`).

## Decisions

### Decision 1: Fixture HTML design — `aria-label` override

The fixture button has `aria-label="action"` (a misleading but non-empty accessible name) so that `get_by_role("button", name="Submit")` finds zero matches (L1 fails with `zero_matches`), while `page.locator(_L2_BUTTON_TAXONOMY_CSS).filter(has_text="Submit")` finds exactly one match (L2 succeeds). This is cleaner than using `aria-label=""` (which some browsers coerce to textContent fallback) and more explicit than CSS `content:` tricks.

**Alternative considered**: Use a `<div role="button">` with no accessible name. Rejected because `div[role=button]` without any visible text would also fail L2; we need visible text.

**Alternative considered**: Use a `<label>` that points to the button but the accessible name is computed differently. Rejected as overly complex for a fixture.

### Decision 2: Where escalation lives — loop `_dispatch`, not inside `locate()`

The existing `_resolve_via_ladder` in `locate.py` already tries L1 → L2 internally. For this ticket, the intent is to exercise the *loop*'s supervisor path, which means `loop.py` must call `locate_l1` directly (or let `locate()` raise on L1 failure) and then invoke the supervisor. Two sub-options:

**Option A**: Call `locate()` (which uses the full internal ladder) — but this means L1 → L2 escalation is already handled inside `locate()` without the supervisor ever being invoked from the loop. The test would pass without wiring the supervisor into the loop. This does not satisfy the acceptance criterion.

**Option B**: In the loop's `read` dispatch, call `locate()` but wrap it with a supervisor-driven retry loop at the loop level. The inner `locate()` still runs its ladder, but if `locate()` itself raises (which it currently does not for zero_matches since the ladder catches it), the supervisor kicks in.

**Option C (chosen)**: Split the `read` dispatch so it calls `locate_l1` first, catches `LocatorMiss`, invokes `Supervisor.handle()`, then calls `locate_l2` (or whichever tier is prescribed). This explicitly exercises the supervisor path from the loop, satisfying the acceptance criterion. The implementation replaces the single `locate(page, intent)` call in `_dispatch` with a supervised two-tier call.

Note: `_resolve_via_ladder` in `locate.py` is *not* called by `_dispatch` currently — `_dispatch` calls the top-level `locate()` which calls `_resolve_via_ladder`. After this change, `_dispatch` for a `read` with intent will use its own supervisor-driven ladder instead of delegating entirely to `locate()`. The existing `locate()` function remains unchanged for callers that want the full self-contained ladder.

### Decision 3: Test placement — extend `test_loop.py`, not a new file

The pattern from ticket #9 puts loop end-to-end tests in `task2/tests/agent/test_loop.py`. Adding the self-correction test there (rather than a new `test_loop_self_correction.py`) keeps the file coherent and avoids proliferating test files. The test follows the same `_FakeLLMClient` + `fixture_server` + `playwright_chromium` pattern.

### Decision 4: `Supervisor` instance scope — created fresh per `_dispatch` invocation

The `Supervisor` tracks attempt counts keyed by `(tier, reason)`. For the test, a fresh `Supervisor` instance per loop run is sufficient and keeps the loop stateless across runs. The `Supervisor` is instantiated inside `loop()` (once per run, not per dispatch call) so its attempt counter accumulates across multiple locate failures in the same run, which is the correct semantics for the escalation cap.

## Risks / Trade-offs

- **`locate()` internal ladder vs. loop-level supervisor**: By having the loop call `locate_l1` directly, we bypass the locator's internal `_resolve_via_ladder`. This means the loop's supervisor and the locator's ladder are two independent escalation mechanisms. This is intentional for testability but could lead to confusion if a future caller expects `locate()` to be the single source of truth for escalation. Mitigation: document clearly in `loop.py` that the supervisor-driven path is the loop's own escalation layer.
- **Fixture fragility**: If Playwright's `filter(has_text=...)` behaviour changes for `aria-label`-overridden buttons, the fixture may stop working as expected. Mitigation: the fixture is simple enough to adjust.
- **`Supervisor.max_attempts` cap**: The supervisor halts after `max_attempts=3` by default. For the test, only one escalation is needed, so this is not a concern.

## Open Questions

(none — all decisions are resolved above)
