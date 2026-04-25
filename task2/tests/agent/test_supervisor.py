from __future__ import annotations

import dataclasses
import inspect

import pytest

from agent.locate import LocatorMiss, locate_l1, locate_l2
from agent.supervisor import EscalationDecision, Supervisor


# ---------------------------------------------------------------------------
# Task 1.2 – construction
# ---------------------------------------------------------------------------


def test_supervisor_constructs_with_defaults():
    sup = Supervisor()
    assert sup is not None


# ---------------------------------------------------------------------------
# Task 1.3 – EscalationDecision is frozen
# ---------------------------------------------------------------------------


def test_escalation_decision_is_frozen():
    dec = EscalationDecision(next_tier="L2_dom", policy="next_tier", attempt=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        dec.next_tier = "L3_rerank"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Task 1.4 – L1 zero-match escalates to L2
# ---------------------------------------------------------------------------


def test_l1_zero_match_escalates_to_l2():
    miss = LocatorMiss(reason="zero_matches", match_count=0)
    sup = Supervisor()
    decision = sup.handle(miss, current_tier="L1_ax")
    assert decision == EscalationDecision(next_tier="L2_dom", policy="next_tier", attempt=1)


# ---------------------------------------------------------------------------
# Task 1.5 – vision_miss halts from L4
# ---------------------------------------------------------------------------


def test_vision_miss_halts_from_l4():
    miss = LocatorMiss(reason="vision_miss", match_count=0)
    decision = Supervisor().handle(miss, current_tier="L4_vision")
    assert decision.next_tier is None
    assert decision.policy == "halt"


# ---------------------------------------------------------------------------
# Task 1.6 – unrecognised tier halts
# ---------------------------------------------------------------------------


def test_unrecognised_tier_halts():
    miss = LocatorMiss(reason="zero_matches", match_count=0)
    decision = Supervisor().handle(miss, current_tier="L2_dom")
    assert decision.next_tier is None
    assert decision.policy == "halt"


# ---------------------------------------------------------------------------
# Task 1.7 – attempt counter increments
# ---------------------------------------------------------------------------


def test_attempt_counter_increments():
    miss = LocatorMiss(reason="zero_matches", match_count=0)
    sup = Supervisor()
    first = sup.handle(miss, current_tier="L1_ax")
    second = sup.handle(miss, current_tier="L1_ax")
    assert first.attempt == 1
    assert second.attempt == 2


# ---------------------------------------------------------------------------
# Task 1.8 – attempt cap triggers halt
# ---------------------------------------------------------------------------


def test_attempt_cap_triggers_halt():
    miss = LocatorMiss(reason="zero_matches", match_count=0)
    sup = Supervisor(max_attempts=2)
    first = sup.handle(miss, current_tier="L1_ax")
    second = sup.handle(miss, current_tier="L1_ax")
    third = sup.handle(miss, current_tier="L1_ax")
    assert first.policy == "next_tier"
    assert second.policy == "next_tier"
    assert third.policy == "halt"
    assert third.attempt == 3


# ---------------------------------------------------------------------------
# Task 1.9 – handle does NOT accept a page argument
# ---------------------------------------------------------------------------


def test_supervisor_does_not_accept_page():
    miss = LocatorMiss(reason="zero_matches", match_count=0)
    sup = Supervisor()
    sig = inspect.signature(sup.handle)
    params = list(sig.parameters.keys())
    assert "page" not in params
    # Should work fine with just miss + current_tier
    dec = sup.handle(miss, current_tier="L1_ax")
    assert dec is not None


# ---------------------------------------------------------------------------
# Task 2.1 – integration test: L1 miss → supervisor escalates → L2 succeeds
# ---------------------------------------------------------------------------


def test_l1_miss_supervisor_escalate_l2_succeeds(fixture_server, playwright_chromium):
    from agent.browser import Browser

    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l2_placeholder.html")
        page = b._page

        # Step 1: L1 misses because the input has no accessible name
        with pytest.raises(LocatorMiss) as excinfo:
            locate_l1(page, role="textbox", name="Email address")
        miss = excinfo.value

        # Step 2: Supervisor decides to escalate to L2
        sup = Supervisor()
        decision = sup.handle(miss, current_tier="L1_ax")
        assert decision.next_tier == "L2_dom"

        # Step 3: Executing the escalation via locate_l2 succeeds
        result = locate_l2(page, role="textbox", name="Email address")
        assert result.tier == "L2_dom"
