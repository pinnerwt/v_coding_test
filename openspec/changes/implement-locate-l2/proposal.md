## Why

Ticket #3 landed L1 (accessibility-tree match) of `agent/locate.py`. L1 only sees what the AX tree exposes, so any element with no accessible name — a placeholder-only `<input>`, a non-semantic `<div class="btn">Submit</div>` that the page nonetheless treats as a click target — is invisible to it. Without L2, every such intent surfaces to the agent loop as a hard `LocatorMiss(reason="zero_matches")` and stalls progress on real-world forms and ad-hoc sites. Ticket #4 adds the **L2 DOM-heuristics tier** that catches these cases and extends the `locate()` orchestrator to fall through L1 → L2 on a zero-match miss.

## What Changes

- Extend `task2/agent/locate.py` with:
  - `locate_l2(page, *, role, name) -> LocateResult` — DOM-heuristic resolver. Tries, in order:
    1. **Placeholder match** for `textbox` (and only `textbox`) — `page.get_by_placeholder(name, exact=False)`.
    2. **Text-contains over clickable affordances** for `button` and `link` — match the visible text of any element in a small per-role DOM taxonomy that includes non-semantic clickables (e.g. `div[onclick]`, `[class*="btn"]`, `span[role=button]`, `a[onclick]`).
    The first strategy that yields exactly one element wins. Returns `tier="L2_dom"`, `confidence=0.7`. Raises `LocatorMiss(reason="zero_matches")` if every strategy returns zero, or `LocatorMiss(reason="ambiguous", match_count=N)` if every non-empty strategy returns >1 (the ambiguous count reflects the first non-empty strategy's count, not the sum, so the supervisor sees a single intelligible number).
  - Extend `locate(page, intent)` so that an L1 `LocatorMiss(reason="zero_matches")` is recovered by calling `locate_l2(page, role=role, name=name)`. L1 `LocatorMiss(reason="ambiguous")` continues to propagate unchanged (L3 rerank, ticket #5, will catch it). L2's own `LocatorMiss` propagates to the caller as-is.
  - Roles outside L2's known set (`heading`, `checkbox` for now) raise `LocatorMiss(reason="zero_matches", match_count=0)` from `locate_l2` immediately — these roles have no DOM heuristic that improves on L1, so falling through is a no-op the supervisor can route to L3/L4.
- Add `task2/tests/fixtures/locate_l2_placeholder.html`: a single `<input placeholder="Email address">` with no label, no `aria-*`, no enclosing `<label>`. L1 misses; L2 placeholder strategy hits.
- Add `task2/tests/fixtures/locate_l2_nonsemantic.html`: a `<div class="btn" onclick="...">Submit</div>` (no role, no aria) that is the only candidate. L1 misses; L2 text-contains-on-clickable hits.
- Add `task2/tests/fixtures/locate_l2_ambiguous.html`: two `<div class="btn">Save</div>` elements in distinct sections — L2 strategy returns 2; `locate_l2` raises `LocatorMiss(reason="ambiguous", match_count=2)`.
- Add `task2/tests/agent/test_locate_l2.py` covering: placeholder happy path, non-semantic-clickable happy path, L2 ambiguous, L2 zero-matches, `locate()` orchestrator falling L1 → L2 on zero-match, `locate()` orchestrator NOT falling through on L1 ambiguous, L2 unsupported-role short-circuit.

Out of scope: L3 semantic rerank (ticket #5), L4 vision (ticket #6), locator cache (ticket #7), supervisor-driven escalation policy (ticket #8). `agent/browser.py` is still not wired for `click(intent)` / `read(intent)`.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `locator-pipeline`: extend the entry point and add the L2 tier. New requirements:
  - **L2 DOM-heuristic resolution** (placeholder for textbox; text-contains over clickable DOM taxonomy for button/link).
  - Updated **Locator pipeline entry point** behavior: `locate()` now cascades L1 → L2 on L1 zero-match; ambiguous L1 still propagates.

## Impact

- **Code**: `task2/agent/locate.py` (new `locate_l2`, modified `locate`); new tests `task2/tests/agent/test_locate_l2.py`; three new fixtures under `task2/tests/fixtures/`.
- **Dependencies**: none new. `page.get_by_placeholder` and `Locator.filter(has_text=...)` are already in the pinned Playwright version.
- **Existing modules**: `agent/browser.py` unchanged. `agent/llm.py` unchanged. Existing L1 tests must keep passing (the cascade only kicks in on `zero_matches`, so L1's ambiguous-fixture tests are unaffected).
- **Deployment**: no Zeabur impact — the agent loop is not yet wired up.
