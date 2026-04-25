## 1. Failing tests (red) — supervisor unit tests

- [ ] 1.1 Create `task2/tests/agent/test_supervisor.py`. Add imports: `from agent.supervisor import Supervisor, EscalationDecision` and `from agent.locate import LocatorMiss`. The import itself will fail until the module exists — that is the first red bar.
- [ ] 1.2 Write `test_supervisor_constructs_with_defaults` — `Supervisor()` constructs without error; the instance exists.
- [ ] 1.3 Write `test_escalation_decision_is_frozen` — construct `EscalationDecision(next_tier="L2_dom", policy="next_tier", attempt=1)`; attempt to assign to a field; assert `dataclasses.FrozenInstanceError` is raised.
- [ ] 1.4 Write `test_l1_zero_match_escalates_to_l2` — given `miss = LocatorMiss(reason="zero_matches", match_count=0)` and `sup = Supervisor()`, assert `sup.handle(miss, current_tier="L1_ax")` returns `EscalationDecision(next_tier="L2_dom", policy="next_tier", attempt=1)`.
- [ ] 1.5 Write `test_vision_miss_halts_from_l4` — given `miss = LocatorMiss(reason="vision_miss", match_count=0)`, assert `Supervisor().handle(miss, current_tier="L4_vision")` returns a decision with `next_tier=None` and `policy="halt"`.
- [ ] 1.6 Write `test_unrecognised_tier_halts` — given `miss = LocatorMiss(reason="zero_matches", match_count=0)`, assert `Supervisor().handle(miss, current_tier="L2_dom")` returns a decision with `next_tier=None` and `policy="halt"` (L2 escalation not yet implemented).
- [ ] 1.7 Write `test_attempt_counter_increments` — call `supervisor.handle(miss, current_tier="L1_ax")` twice on the same `Supervisor()` instance; assert the second call returns `attempt=2`.
- [ ] 1.8 Write `test_attempt_cap_triggers_halt` — use `Supervisor(max_attempts=2)`; call `handle(miss, current_tier="L1_ax")` three times; assert the first two return `policy="next_tier"` and the third returns `policy="halt"` with `attempt=3`.
- [ ] 1.9 Write `test_supervisor_does_not_accept_page` — verify `Supervisor.handle` signature does NOT take a `page` positional argument (the supervisor is browser-free). Use `inspect.signature` or simply assert that `handle(miss, current_tier="L1_ax")` succeeds with only those two args and no page.
- [ ] 1.10 From `task2/`, run `uv run pytest tests/agent/test_supervisor.py -x` and confirm all tests fail for the expected reason (ImportError on `agent.supervisor`).

## 2. Failing test (red) — integration acceptance test

- [ ] 2.1 In `task2/tests/agent/test_supervisor.py`, add an integration test `test_l1_miss_supervisor_escalate_l2_succeeds` that:
  - Loads the existing `locate_l2.html` fixture (it has `<input placeholder="Email address">` but no accessible name — the exact scenario for L1 miss + L2 hit).
  - Calls `locate_l1(page, role="textbox", name="Email address")` inside a `pytest.raises(LocatorMiss)` block; captures the exception.
  - Constructs `Supervisor()`, calls `supervisor.handle(miss, current_tier="L1_ax")`, asserts `decision.next_tier == "L2_dom"`.
  - Calls `locate_l2(page, role="textbox", name="Email address")` and asserts the result `tier == "L2_dom"`.
  - This test requires the `playwright_chromium` + `fixture_server` fixtures from `conftest.py` (already present).
- [ ] 2.2 From `task2/`, run `uv run pytest tests/agent/test_supervisor.py::test_l1_miss_supervisor_escalate_l2_succeeds -x` and confirm it fails with `ImportError` on `agent.supervisor`.

## 3. Implementation (green) — `supervisor.py` module

- [ ] 3.1 Create `task2/agent/supervisor.py` with module-level imports: `from __future__ import annotations`, `import dataclasses`, `from dataclasses import dataclass`. Do NOT import `agent.browser`, `agent.llm`, `agent.locator_cache`, or `playwright`.
- [ ] 3.2 Import `LocatorMiss` from `agent.locate` at the top of `supervisor.py`.
- [ ] 3.3 Define the frozen dataclass `EscalationDecision` with fields `next_tier: str | None`, `policy: str`, `attempt: int`.
- [ ] 3.4 Define the escalation table as a module-level constant — a mapping from `(current_tier: str, miss_reason: str)` to `next_tier: str` — covering exactly the implemented rows:
  - `("L1_ax", "zero_matches")` → `"L2_dom"`.
  Do NOT add L1 ambiguous → L3, L2 → L3, or L3 → L4 entries; those rows are out of scope for this ticket.
- [ ] 3.5 Define the `Supervisor` class:
  - `__init__(self, *, max_attempts: int = 3)` — store `self._max_attempts = max_attempts` and `self._attempts: dict[tuple[str, str], int] = {}`.
  - `handle(self, miss: LocatorMiss, *, current_tier: str) -> EscalationDecision`:
    - Build the key `(current_tier, miss.reason)`.
    - Increment `self._attempts[key]` (default 0 before increment).
    - If `self._attempts[key] > self._max_attempts`: return `EscalationDecision(next_tier=None, policy="halt", attempt=self._attempts[key])`.
    - Look up the key in the escalation table. If found: return `EscalationDecision(next_tier=<value>, policy="next_tier", attempt=self._attempts[key])`.
    - Otherwise: return `EscalationDecision(next_tier=None, policy="halt", attempt=self._attempts[key])`.
- [ ] 3.6 From `task2/`, run `uv run pytest tests/agent/test_supervisor.py -x` and confirm all unit tests pass.
- [ ] 3.7 From `task2/`, run `uv run pytest tests/agent/test_supervisor.py::test_l1_miss_supervisor_escalate_l2_succeeds` and confirm the integration test passes.

## 4. Full suite validation (green bar)

- [ ] 4.1 From `task2/`, run `uv run pytest tests/agent/test_supervisor.py` (all tests, no `-x`) and confirm all pass.
- [ ] 4.2 From `task2/`, run `uv run pytest` (full suite) and confirm existing tickets #1–#7 tests remain green (`test_llm.py`, `test_browser.py`, `test_locate.py`, `test_locate_l2.py`, `test_locate_l3.py`, `test_locate_l4.py`, `test_locator_cache.py` are unaffected).

## 5. Refactor + housekeeping

- [ ] 5.1 Reread `task2/agent/supervisor.py`. Check: is the escalation table a clean module-level constant? Are type hints present on all public methods? Is there any dead code?
- [ ] 5.2 Confirm `agent/locate.py`, `agent/browser.py`, `agent/llm.py`, `agent/locator_cache.py` are UNCHANGED (no modifications introduced by this ticket).
- [ ] 5.3 Confirm `task2/pyproject.toml` has no new dependencies (the supervisor uses only stdlib + `agent.locate`).

## 6. Pre-commit gate

- [ ] 6.1 From `task2/`, run `uv run ruff format .` — confirm no files are reformatted (code was written clean).
- [ ] 6.2 From `task2/`, run `uv run ruff check .` — confirm zero lint errors.
- [ ] 6.3 From `task2/`, run `uv run pytest` — confirm full suite passes.
- [ ] 6.4 Commit with conventional message: `feat(task2): add supervisor module with L1-zero-match escalation to L2`.
