## Context

`task2/agent/locate.py` after ticket #7 is a complete locator pipeline: `locate(page, intent, *, llm_chat=None, cache=None)` drives L1 → L2/L3 → L4 through `_resolve_via_ladder`, raises `LocatorMiss` on exhaustion, and writes to the locator cache on success. The pipeline is correct for the "full cascade in one call" use case, but the existing `_resolve_via_ladder` internal function is opaque from the outside: callers cannot inspect *which tier failed*, *why*, or *what the next strategy should be*.

Ticket #8 introduces `supervisor.py` as the first component above the pipeline. Its job is narrow: observe a `LocatorMiss`, classify its cause, and decide which tier to escalate to next. The agent loop (ticket #9) will own actually executing that escalation; the supervisor only produces the decision.

Constraints:

- **TDD non-negotiable.** Tests before code. The acceptance criterion is a synthetic `LocatorMiss(reason="zero_matches", match_count=0)` → escalation decision "try L2" → executing `locate_l2` succeeds on a compatible fixture page.
- **`uv` + `ruff` only.** Lint clean before marking done.
- **No hardcoded LLM provider.** The supervisor does not call an LLM; the constraint is inherited for completeness.
- **No abstractions for hypothetical second callers.** The only consumer today is the test suite (directly) and `loop.py` (ticket #9). No plugin system, no registry.
- **`LocatorMiss` stays in `agent/locate.py`.** It was already placed there in ticket #3 and all existing tests import it from there. Moving it would require a multifile change with no ticket driving it.

## Goals / Non-Goals

**Goals:**

- A `Supervisor` class in a new `task2/agent/supervisor.py` exposing exactly:
  - `__init__(self, *, max_attempts: int = 3)` — constructor, configurable attempt cap per strategy (default 3 from plan line 66: "caps at 3 strategies × 2 attempts").
  - `handle(self, miss: LocatorMiss, *, current_tier: str) -> EscalationDecision` — given a `LocatorMiss` and the tier that raised it, return an `EscalationDecision`.
- An `EscalationDecision` named tuple (or frozen dataclass — see Decisions) with:
  - `next_tier: str | None` — the tier to try next (`"L2_dom"`, `"L3_rerank"`, `"L4_vision"`, or `None` meaning "give up").
  - `policy: str` — human-readable policy label (mirrors `SupervisorEvent.policy` from `plan.md` line 158: `"next_tier"` or `"halt"`).
  - `attempt: int` — the attempt number within this strategy (for logging; the supervisor increments it).
- The escalation table (this change: L1 tier only):

  | `current_tier` | `miss.reason`   | `next_tier`  | `policy`     |
  |---|---|---|---|
  | `"L1_ax"`      | `"zero_matches"` | `"L2_dom"`   | `"next_tier"` |
  | `"L1_ax"`      | `"ambiguous"`    | `"L3_rerank"` | `"next_tier"` |
  | any            | `"vision_miss"`  | `None`        | `"halt"`      |
  | any (exhausted) | any             | `None`        | `"halt"`      |

  (L2→L3, L3→L4, L4→None are documented as future rows and SHALL NOT be implemented in this change.)

- Tests in `task2/tests/agent/test_supervisor.py` (TDD: failing tests before implementation).
- Lint clean, full pytest green.

**Non-Goals:**

- Wiring the supervisor into `loop.py`. `loop.py` does not exist yet (ticket #9); the supervisor is designed in anticipation of it.
- Implementing L2→L3 or L3→L4 escalation in the supervisor. Those rows in the table are mentioned for orientation only. The `_resolve_via_ladder` inside `locate.py` already handles L2→L4 internally; a future ticket may refactor that into the supervisor.
- Emitting `SupervisorEvent` trace records (ticket #12). The supervisor's return value carries the fields the trace writer will need, but the write happens in the loop, not here.
- A `SupervisedLocate` wrapper that calls both the locator and the supervisor in one shot. The two remain separate; the loop composes them.
- Multi-strategy caps or per-site policy overrides. The default `max_attempts=3` is enforced by the supervisor's internal counter; the plan's "3 strategies × 2 attempts" model is for the loop ticket.
- Moving `LocatorMiss` to a shared `exceptions.py`. The existing import path `from agent.locate import LocatorMiss` is used by all existing tests and SHALL remain stable.

## Decisions

### Module shape: class (`Supervisor`) not a standalone function

A stateless function `supervise(miss, current_tier)` would work for the ticket #8 acceptance test, but the plan's escalation model (line 66: "caps at 3 strategies × 2 attempts before declaring `failed`") implies the supervisor needs to track per-run attempt state. A class with `max_attempts` and an internal counter is the minimal shape that satisfies both today (ticket #8, no counter needed in the test) and tomorrow (ticket #9, loop wires a per-run supervisor instance).

Alternative considered: a stateless function with an external attempt counter passed as a parameter. Rejected — the counter is exactly the kind of accumulated state the loop should not be responsible for; it belongs in the supervisor.

Alternative considered: a class with an `attempt_table: dict[str, int]` tracking attempts per strategy. Accepted as-is — the `attempt` field in `EscalationDecision` carries the current count for the caller's logging use; the supervisor increments an internal `_attempts` dict keyed by `(current_tier, reason)`.

### `EscalationDecision`: frozen dataclass, not named tuple

Named tuple fields are positional and easy to swap accidentally. A frozen dataclass with keyword-only construction is safer. It also makes adding fields (e.g. `rationale: str` for ticket #12) backwards-compatible with keyword-only callers.

```python
@dataclass(frozen=True)
class EscalationDecision:
    next_tier: str | None   # "L2_dom" | "L3_rerank" | "L4_vision" | None
    policy: str             # "next_tier" | "halt"
    attempt: int            # current attempt count for this strategy path
```

Alternative considered: `typing.NamedTuple`. Rejected — positional access is error-prone; frozen dataclass is the standard choice in this codebase (see `CacheEntry`, `LocateResult`).

Alternative considered: `enum.Enum` for `policy`. Rejected — the plan's `SupervisorEvent.policy` field is a plain string in the trace schema, and the CLAUDE.md warns against abstractions for hypothetical second callers.

### Escalation table: minimal (L1 only) for this change

The ticket text is "synthetic '0 matches' error → `LocatorMiss` → escalate to L2." Only the L1 zero-match row is required. L1 ambiguous → L3, L2 miss → L3, etc. are documented in the table above and in the spec, but not implemented.

Decision: implement exactly the rows the failing tests demand. The `handle()` method will reach a `halt` decision for any tier it does not recognise, which is the correct safe fallback.

Alternative considered: implement all four rows now (L1_ax, L2_dom, L3_rerank, L4_vision). Rejected — TDD rule: write the minimal code that makes the failing test pass. The loop ticket will drive the remaining rows.

### `LocatorMiss` import source: `agent.locate`, not a shared `exceptions.py`

`LocatorMiss` is defined in `agent/locate.py` (line 109). All existing tests import it from there. Introducing a new `agent/exceptions.py` and re-exporting would be a refactor ticket of its own; it is not needed for ticket #8 and would touch existing passing tests.

### Tests: mock the locator, not the browser

The acceptance test (synthetic L1 miss → escalate to L2 → succeed) can be written in two ways:

1. **Unit test against the supervisor alone** — construct a `LocatorMiss(reason="zero_matches", match_count=0)`, call `supervisor.handle(miss, current_tier="L1_ax")`, assert `decision.next_tier == "L2_dom"`. This is the primary test and does not need a browser.
2. **Integration test** — spin up a fixture page where L1 deliberately misses and L2 succeeds, run the full supervisor → execute decision → `locate_l2` path. This verifies the end-to-end escalation is correct.

Both are included. The unit tests (sections 2 and 3 of `tasks.md`) have no browser dependency. The integration test (section 4) reuses the existing `playwright_chromium` + `fixture_server` fixtures and the `locate_l2.html` fixture from ticket #4, since that fixture was specifically authored to have no accessible name on the input (L1 misses, L2 via placeholder succeeds).

Alternative considered: only unit tests. Rejected — the CLAUDE.md rule is "mock the network, not the contract." The supervisor's contract includes the ability to compose with `locate_l2`; testing that composition against a real (local) browser fixture is required.

### Module import structure

`agent/supervisor.py` imports:
- `from __future__ import annotations`
- `from dataclasses import dataclass`
- `from agent.locate import LocatorMiss`

It does NOT import `agent.llm`, `agent.browser`, `agent.locator_cache`, or `playwright`. The supervisor is a pure decision-making module with no I/O.

The lazy-import pattern used for LLM chat functions in `locate.py` is NOT needed here because the supervisor's import of `LocatorMiss` from `agent.locate` is a pure class reference — no network calls, no side effects at module load.

## Risks / Trade-offs

- **`_resolve_via_ladder` in `locate.py` already does L1→L2 internally.** The supervisor introduces a *second* escalation path from the caller's perspective. If `loop.py` calls `locate()` (which internalises the ladder) and the supervisor independently observes a miss, there is a logical duplication. Mitigation: ticket #9 will decide whether `loop.py` bypasses `locate()` in favour of calling individual tiers + supervisor, or calls `locate()` for the happy path and the supervisor only for loop-level recovery. That decision is for ticket #9; this ticket only ensures the supervisor is correct in isolation.

- **Attempt counter resets per `Supervisor` instance.** If the loop constructs a new `Supervisor` per step rather than per task, the per-task "3 strategies × 2 attempts" cap is not enforced. Mitigation: document in the class docstring that one `Supervisor` per task-run is the expected usage. Ticket #9 enforces this.

- **L1 ambiguous → L3 row in the table is described but not tested.** It appears in the escalation table in the spec for completeness; a test that asserts it is not included in this change (the ticket only asks for "0 matches" → L2). If someone implements the L1 ambiguous row incidentally, the test suite will not catch a regression. Mitigation: the spec includes a `SHOULD NOT implement` annotation on that row; the tasks.md keeps it out of scope explicitly.

- **Frozen dataclass `EscalationDecision` is not JSON-serialisable out of the box.** `SupervisorEvent` (plan line 154) will need `dataclasses.asdict` or a custom encoder. Mitigation: ticket #12 (trace writer) owns serialisation. The supervisor just produces the dataclass.
