from __future__ import annotations

from dataclasses import dataclass

from agent.locate import LocatorMiss
from agent.trace import EscalationPolicy

# Only implemented escalation row. L2→L3, L3→L4, and L1-ambiguous→L3 are
# deliberately absent so unknown (tier, reason) pairs fall through to halt.
_ESCALATION_TABLE: dict[tuple[str, str], str] = {
    ("L1_ax", "zero_matches"): "L2_dom",
}

# T6: per-run replan budget with monotone escalation. Each replan must be
# triggered by a strictly stronger classification than the previous one to
# prevent oscillation. Unknown classifications get severity 0 so they can
# never escalate past a known prior classification.
_REPLAN_SEVERITY: dict[str, int] = {
    "off_plan": 1,
    "tool_error": 2,
    "unsupported_done": 3,
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
