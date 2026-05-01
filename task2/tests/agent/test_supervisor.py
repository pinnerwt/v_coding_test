from __future__ import annotations

import dataclasses
import inspect

import pytest

from agent.locate import LocatorMiss, locate_l1, locate_l2
from agent.supervisor import EscalationDecision, Supervisor
from agent.trace import EscalationPolicy


def test_escalation_decision_policy_annotated_as_escalation_policy():
    import typing

    hints = typing.get_type_hints(EscalationDecision)
    assert hints["policy"] is EscalationPolicy


def test_supervisor_constructs_with_defaults():
    sup = Supervisor()
    assert sup is not None


def test_escalation_decision_is_frozen():
    dec = EscalationDecision(next_tier="L2_dom", policy="next_tier", attempt=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        dec.next_tier = "L3_rerank"  # type: ignore[misc]


def test_l1_zero_match_escalates_to_l2():
    miss = LocatorMiss(reason="zero_matches", match_count=0)
    sup = Supervisor()
    decision = sup.handle(miss, current_tier="L1_ax")
    assert decision == EscalationDecision(next_tier="L2_dom", policy="next_tier", attempt=1)


def test_vision_miss_halts_from_l4():
    miss = LocatorMiss(reason="vision_miss", match_count=0)
    decision = Supervisor().handle(miss, current_tier="L4_vision")
    assert decision.next_tier is None
    assert decision.policy == "halt"


def test_unrecognised_tier_halts():
    miss = LocatorMiss(reason="zero_matches", match_count=0)
    decision = Supervisor().handle(miss, current_tier="L2_dom")
    assert decision.next_tier is None
    assert decision.policy == "halt"


def test_attempt_counter_increments():
    miss = LocatorMiss(reason="zero_matches", match_count=0)
    sup = Supervisor()
    first = sup.handle(miss, current_tier="L1_ax")
    second = sup.handle(miss, current_tier="L1_ax")
    assert first.attempt == 1
    assert second.attempt == 2


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


def test_supervisor_does_not_accept_page():
    miss = LocatorMiss(reason="zero_matches", match_count=0)
    sup = Supervisor()
    sig = inspect.signature(sup.handle)
    assert "page" not in sig.parameters
    dec = sup.handle(miss, current_tier="L1_ax")
    assert dec is not None


def test_l1_miss_supervisor_escalate_l2_succeeds(fixture_server, playwright_chromium):
    from agent.browser import Browser

    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l2_nonsemantic.html")
        page = b._page

        with pytest.raises(LocatorMiss) as excinfo:
            locate_l1(page, role="button", name="Submit")
        miss = excinfo.value
        assert miss.reason == "zero_matches"

        sup = Supervisor()
        decision = sup.handle(miss, current_tier="L1_ax")
        assert decision.next_tier == "L2_dom"

        result = locate_l2(page, role="button", name="Submit")
        assert result.tier == "L2_dom"


def test_supervisor_last_policy_is_none_on_construction():
    sup = Supervisor()
    assert sup.last_policy is None


def test_supervisor_last_policy_reflects_next_tier():
    miss = LocatorMiss(reason="zero_matches", match_count=0)
    sup = Supervisor()
    decision = sup.handle(miss, current_tier="L1_ax")
    assert decision.policy == "next_tier"
    assert sup.last_policy == "next_tier"


def test_supervisor_last_policy_is_halt_after_exhaustion():
    miss = LocatorMiss(reason="zero_matches", match_count=0)
    sup = Supervisor(max_attempts=1)
    sup.handle(miss, current_tier="L1_ax")
    sup.handle(miss, current_tier="L1_ax")
    assert sup.last_policy == "halt"


def test_supervisor_replan_state_is_empty_on_construction():
    sup = Supervisor()
    assert sup.replans_used == 0
    assert sup.last_replan_classification is None


# ---------------------------------------------------------------------------
# T6 — multi-replan budget with monotone escalation
# ---------------------------------------------------------------------------


def test_can_replan_returns_true_for_first_replan_any_classification():
    """With no prior replan, any classification is allowed."""
    for cls in ("off_plan", "tool_error", "unsupported_done"):
        sup = Supervisor()
        assert sup.can_replan(cls) is True, f"first replan must be allowed for {cls!r}"


def test_record_replan_increments_counter_and_stores_classification():
    sup = Supervisor()
    sup.record_replan("off_plan")
    assert sup.replans_used == 1
    assert sup.last_replan_classification == "off_plan"
    sup.record_replan("tool_error")
    assert sup.replans_used == 2
    assert sup.last_replan_classification == "tool_error"


def test_can_replan_rejects_repeat_of_same_classification():
    """Oscillation guard: same classification twice in a row is rejected."""
    sup = Supervisor()
    sup.record_replan("off_plan")
    assert sup.can_replan("off_plan") is False


def test_can_replan_rejects_weaker_classification_after_stronger():
    """Monotone: tool_error after unsupported_done is weaker, must be rejected."""
    sup = Supervisor()
    sup.record_replan("unsupported_done")
    assert sup.can_replan("tool_error") is False
    assert sup.can_replan("off_plan") is False


def test_can_replan_accepts_strictly_stronger_classification():
    """Escalation chain off_plan → tool_error → unsupported_done is allowed."""
    sup = Supervisor()
    sup.record_replan("off_plan")
    assert sup.can_replan("tool_error") is True
    sup.record_replan("tool_error")
    assert sup.can_replan("unsupported_done") is True


def test_can_replan_respects_budget_cap_of_three():
    """Even under monotone escalation the cap of 3 holds."""
    sup = Supervisor()
    sup.record_replan("off_plan")
    sup.record_replan("tool_error")
    sup.record_replan("unsupported_done")
    assert sup.replans_used == 3
    # No classification stronger than unsupported_done exists, but the cap
    # alone must already deny further replans.
    assert sup.can_replan("unsupported_done") is False


def test_can_replan_unknown_classification_is_treated_as_lowest_severity():
    """Unknown classifications fall through to severity 0 — never strong enough
    to escalate from any known prior classification."""
    sup = Supervisor()
    sup.record_replan("off_plan")
    assert sup.can_replan("mystery") is False
