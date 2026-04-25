## Why

Task 2's agent loop targets elements by **intent** ("Submit button"), not raw selectors (`task2/plan.md` §Architecture, `agent/browser.py` and `agent/locate.py`). Ticket #3 carves out the smallest TDD slice of the locator pipeline: **L1 — accessibility-tree match by role + accessible name**. L1 is the primary, drift-resilient tier; everything later (L2 DOM heuristics, L3 semantic rerank, L4 vision) only runs when L1 misses. Without L1 there is nothing for `agent/loop.py`, `agent/supervisor.py`, or the locator cache (tickets #7–#11) to build on.

## What Changes

- Add `task2/agent/locate.py` with:
  - A `LocateResult` dataclass carrying `{ tier, role, name, selector, ax_fingerprint, confidence }` — the shape every later tier (L2–L4) and the locator cache (ticket #7) will share.
  - A `LocateError` base + `IntentParseError` and `LocatorMiss` typed exceptions.
  - A small intent parser `parse_intent(intent) -> (role, name)`. Initial role vocabulary covers the ARIA roles needed by ticket #3 and immediate downstream tickets: `button`, `link`, `textbox`, `checkbox`, `heading`. Articles (`the`, `a`, `an`) are stripped from the front.
  - `locate_l1(page, *, role, name) -> LocateResult` that resolves via Playwright's `page.get_by_role(role, name=name, exact=False)`, returns the unique match, raises `LocatorMiss` on zero matches, and raises `LocatorMiss(reason="ambiguous")` on >1 matches (escalation to L2/L3 is a later ticket — L1's contract is "I have a unique answer or I don't").
  - `locate(page, intent) -> LocateResult` orchestrator that runs L1 only for now; later tickets extend it with L2–L4.
- Add `task2/tests/fixtures/locate_l1.html`: a page with a real `<button>Submit</button>`, a `<div role="button" aria-label="Cancel">` AX-spoofer (different accessible name), and a `<div class="btn">Submit</div>` non-semantic look-alike that should be invisible to the AX tree.
- Add `task2/tests/agent/test_locate.py` covering: intent parsing happy path + failures, L1 happy path against the fixture, L1 zero-match and ambiguous-match outcomes, and the `locate()` orchestrator returning an L1 result.

Out of scope for this change: L2 DOM heuristics, L3 semantic rerank, L4 vision fallback, the locator cache, intent-based wiring into `agent/browser.py`. Those are tickets #4–#7 and the future `click(intent)` work.

## Capabilities

### New Capabilities

- `locator-pipeline`: intent → element resolution via a tiered strategy (L1–L4 in `task2/plan.md`). This change introduces the capability with **L1 (accessibility-tree match) and the shared `LocateResult` / exception surface only**. Later tickets extend the same capability with additional tiers and the cache.

### Modified Capabilities

(none)

## Impact

- **Code**: new module `task2/agent/locate.py`; new test module `task2/tests/agent/test_locate.py`; new fixture `task2/tests/fixtures/locate_l1.html`.
- **Dependencies**: none new. Playwright's accessibility query (`page.get_by_role`) is already available via the `playwright` dep added in ticket #2.
- **Existing modules**: `agent/browser.py` is **not** modified by this change — `read(selector)` stays selector-based until intent-based `read(intent)` lands with the rest of the tool surface.
- **Deployment**: no Zeabur impact — the agent loop is not yet wired up.
