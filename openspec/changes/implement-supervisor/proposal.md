## Why

The locator pipeline (L1 → L2 → L3 → L4) in `agent/locate.py` raises `LocatorMiss` when no tier can resolve an intent, but nothing above the pipeline currently catches that signal and acts on it. Ticket #8 in `task2/plan.md` closes this gap: when the pipeline reports a miss (specifically a "0 matches" result at a given tier), a supervisor module must classify it as `LocatorMiss`, decide on a recovery policy, and escalate — concretely, L1 miss → escalate to L2. Without the supervisor, a `LocatorMiss` propagates unhandled to the caller; with it, the agent loop gets a clear escalation hook it can route through in tickets #9–#11.

## What Changes

- Add a new module `task2/agent/supervisor.py` exposing a `Supervisor` class (or `supervise()` function — settled in design) that:
  - Accepts a `LocatorMiss` exception plus the current tier context.
  - Classifies it against the escalation table (L1 zero-match → escalate to L2; L1 ambiguous → already handled by the L3/L4 ladder inside `locate()`; future: L2 miss → L3, L3 miss → L4).
  - Returns an escalation decision (next tier to attempt, or "give up") that the caller can execute.
- The `LocatorMiss` exception class already lives in `agent/locate.py` — no new exception module is introduced. The supervisor imports from `agent.locate`.
- Tests live in `task2/tests/agent/test_supervisor.py`. The acceptance test is: a synthetic `LocatorMiss(reason="zero_matches", match_count=0)` from a mocked L1 call produces an escalation decision of "try L2", and executing that decision via `locate_l2` on a compatible fixture page succeeds.
- No changes to `agent/locate.py`, `agent/browser.py`, `agent/llm.py`, or `agent/locator_cache.py`.

Out of scope for this change: wiring the supervisor into `loop.py` (ticket #9), L2→L3 escalation (future), L3→L4 escalation (future, noting the `_resolve_via_ladder` in `locate.py` already does it internally), the full `SupervisorEvent` trace writer (ticket #12), multi-strategy caps described in the plan.

## Capabilities

### New Capabilities

- `supervisor-escalation`: A supervisor module that classifies `LocatorMiss` exceptions and returns an escalation decision. Scope for this change: L1 zero-match → escalate to L2. The module is intentionally minimal — the acceptance test drives L1→L2; L2→L3 and L3→L4 are documented as future scope.

### Modified Capabilities

(none — no existing spec-level requirement changes)

## Impact

- **Code**: new `task2/agent/supervisor.py`; new `task2/tests/agent/test_supervisor.py`.
- **Dependencies**: none new. The supervisor imports only from `agent.locate` (already present) and the Python stdlib.
- **Existing modules**: `agent/locate.py` unchanged (the `LocatorMiss` class and `locate_l2` are already there). `agent/browser.py`, `agent/llm.py`, `agent/locator_cache.py` unchanged.
- **Future tickets**: `loop.py` (ticket #9) will import the supervisor and thread it through the act-observe loop. The supervisor's API surface is designed in anticipation of that caller.
