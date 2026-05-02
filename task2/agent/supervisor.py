from __future__ import annotations

from dataclasses import dataclass

from agent.locate import LocatorMiss
from agent.trace import EscalationPolicy

# Escalation rows the supervisor blesses when invoked from the loop. The
# canonical locator ladder (`agent.locate._resolve_via_ladder`) handles the
# remaining transitions internally — the loop only consults the supervisor
# at L1_ax to record the attempt and decide whether to halt under
# `max_attempts`. F22: ambiguous L1 must reach L3_rerank so cross-language
# accessible-name mismatches are recoverable.
_ESCALATION_TABLE: dict[tuple[str, str], str] = {
    ("L1_ax", "zero_matches"): "L2_dom",
    ("L1_ax", "ambiguous"): "L3_rerank",
}

# T6: per-run replan budget with monotone escalation. Each replan must be
# triggered by a strictly stronger classification than the previous one to
# prevent oscillation. Unknown classifications get severity 0 so they can
# never escalate past a known prior classification.
_REPLAN_SEVERITY: dict[str, int] = {
    "off_plan": 1,
    "tool_error": 2,
    # F20: list-shape comparison-superlative mismatch sits between tool_error
    # and unsupported_done so a structural list-coverage signal can fire first
    # and an LLM-judge unsupported_done can still escalate above it.
    "unsupported_superlative": 3,
    "unsupported_done": 4,
}
_DEFAULT_MAX_REPLANS: int = 3


@dataclass(frozen=True)
class EscalationDecision:
    next_tier: str | None
    policy: EscalationPolicy
    attempt: int


class Supervisor:
    def __init__(
        self,
        *,
        max_attempts: int = 3,
        max_replans: int = _DEFAULT_MAX_REPLANS,
    ) -> None:
        self._max_attempts = max_attempts
        self._max_replans = max_replans
        self._attempts: dict[tuple[str, str], int] = {}
        self.last_policy: EscalationPolicy | None = None
        self.replans_used: int = 0
        self.last_replan_classification: str | None = None

    def total_attempts(self) -> int:
        return sum(self._attempts.values())

    def can_replan(self, classification: str) -> bool:
        if self.replans_used >= self._max_replans:
            return False
        if self.last_replan_classification is None:
            return True
        prev = _REPLAN_SEVERITY.get(self.last_replan_classification, 0)
        new = _REPLAN_SEVERITY.get(classification, 0)
        return new > prev

    def record_replan(self, classification: str) -> None:
        self.replans_used += 1
        self.last_replan_classification = classification

    def handle(self, miss: LocatorMiss, *, current_tier: str) -> EscalationDecision:
        key = (current_tier, miss.reason)
        attempt = self._attempts.get(key, 0) + 1
        self._attempts[key] = attempt

        if attempt > self._max_attempts:
            decision = EscalationDecision(next_tier=None, policy="halt", attempt=attempt)
            self.last_policy = decision.policy
            return decision

        next_tier = _ESCALATION_TABLE.get(key)
        if next_tier is not None:
            decision = EscalationDecision(next_tier=next_tier, policy="next_tier", attempt=attempt)
            self.last_policy = decision.policy
            return decision

        decision = EscalationDecision(next_tier=None, policy="halt", attempt=attempt)
        self.last_policy = decision.policy
        return decision
