## Why

Tickets #3 and #4 landed L1 (accessibility-tree) and L2 (DOM heuristics) of `agent/locate.py`. Both tiers hold the same per-strategy contract: "exactly one match wins, otherwise miss." On real sites that is not enough — the same accessible name (e.g. three sections each containing a `<button>Save</button>`) produces a `LocatorMiss(reason="ambiguous")` that L1/L2 cannot break on their own. Without a tier that brings *semantic* context to bear, every page with repeated affordances stalls the agent. Ticket #5 adds the **L3 semantic rerank tier**: when L1 returns ambiguous, the LLM picks among the candidate elements using each candidate's surrounding text (section heading + a small nearby text snippet) and the parsed intent.

## What Changes

- Extend `task2/agent/locate.py` with:
  - `locate_l3(page, *, role, name, llm_chat=None) -> LocateResult` — semantic rerank tier. Re-runs the L1 AX-tree query (`page.get_by_role(role, name=name, exact=False)`) to gather candidates, captures up to `K = 10` candidates with their accessible name, nearest section heading, and a bounded nearby-text snippet, sends a single rerank prompt to the LLM (`agent.llm.chat` by default, overridable via the `llm_chat` parameter for tests), parses the LLM's structured `{"index": int}` reply, and returns a `LocateResult(tier="L3_rerank", confidence=0.8)` for the chosen candidate. If the AX-tree query yields exactly one match, `locate_l3` SHALL trivially return it as `L3_rerank` (so direct callers get a consistent result shape). If it yields zero matches, `locate_l3` SHALL raise `LocatorMiss(reason="zero_matches", match_count=0)`. If the LLM reply is invalid or out of range, `locate_l3` SHALL raise `LocatorMiss(reason="ambiguous", match_count=N)` carrying the candidate count, so the supervisor (ticket #8, later) can route on it.
  - Extend `locate(page, intent, *, llm_chat=None)` so an L1 `LocatorMiss(reason="ambiguous")` is recovered by calling `locate_l3(page, role=role, name=name, llm_chat=llm_chat)` and returning its result. The existing L1 `zero_matches` → L2 cascade is unchanged. L2 ambiguous still propagates as ambiguous (deferred to a later ticket) — ticket #5's scope is "L1 ambiguous → L3 rerank", per `task2/plan.md`.
  - Add the per-tier confidence value `0.8` for L3, slotting between L2 (`0.7`) and L1 (`1.0`).
- Add `task2/tests/fixtures/locate_l3_three_save.html`: three `<button>Save</button>` elements in three distinct `<section>`s with different headings (e.g. "Profile", "Settings", "Documents"). L1 returns ambiguous (count=3); L3 with a mocked LLM returning `{"index": N}` picks one.
- Update `task2/tests/agent/test_locate_l2.py::test_locate_orchestrator_does_not_cascade_on_l1_ambiguous` to reflect the new orchestrator behaviour: rename to `test_locate_orchestrator_cascades_l1_ambiguous_to_l3` and assert that, when invoked with a stub `llm_chat`, `locate()` returns an `L3_rerank` result instead of propagating the `LocatorMiss`. The locator-pipeline spec scenario for L1 ambiguous propagation is removed; the new "L1 ambiguous → L3" scenario takes its place.
- Add `task2/tests/agent/test_locate_l3.py` covering: trivial single-candidate fallthrough, three-candidate happy path with mocked LLM picking the middle index, zero-candidate miss, malformed LLM reply (non-JSON / index out of range) → `LocatorMiss(reason="ambiguous")`, orchestrator cascade L1 ambiguous → L3, fingerprint stable across runs that pick the same section.

Out of scope: L4 vision fallback (ticket #6), locator cache (ticket #7), supervisor escalation (ticket #8). The L3 prompt itself is intentionally minimal — no chain-of-thought, no candidate-text trimming heuristics beyond a hard char cap; richer prompts can come when the eval set demands them.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `locator-pipeline`: extend the entry point and add the L3 tier. New requirements:
  - **L3 semantic-rerank resolution** (LLM picks among AX-tree candidates given intent + nearby text + section heading).
  - Updated **Locator pipeline entry point** behavior: `locate()` now cascades L1 `ambiguous` → L3, in addition to the existing L1 `zero_matches` → L2 cascade. `locate()` accepts an optional `llm_chat` parameter that is forwarded to L3.

## Impact

- **Code**: `task2/agent/locate.py` (new `locate_l3`, modified `locate`); new tests `task2/tests/agent/test_locate_l3.py`; one new fixture `task2/tests/fixtures/locate_l3_three_save.html`; one modified existing test in `test_locate_l2.py`.
- **Dependencies**: none new. Reuses `agent.llm.chat` and `agent.llm.ChatResponse` already shipped in ticket #1.
- **Existing modules**: `agent/llm.py` unchanged. `agent/browser.py` unchanged. L1 and L2 paths are unchanged; only the orchestrator's recovery on L1 ambiguous changes.
- **Deployment**: no Zeabur impact — the agent loop is not yet wired up, so production traffic does not reach `locate_l3` in this ticket.
