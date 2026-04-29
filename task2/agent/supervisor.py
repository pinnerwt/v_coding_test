from __future__ import annotations

from dataclasses import dataclass

from agent.locate import LocatorMiss
from agent.trace import EscalationPolicy

# Only implemented escalation row. L2→L3, L3→L4, and L1-ambiguous→L3 are
# deliberately absent so unknown (tier, reason) pairs fall through to halt.
_ESCALATION_TABLE: dict[tuple[str, str], str] = {
    ("L1_ax", "zero_matches"): "L2_dom",
}


@dataclass(frozen=True)
class EscalationDecision:
    next_tier: str | None
    policy: EscalationPolicy
    attempt: int


class Supervisor:
    def __init__(self, *, max_attempts: int = 3) -> None:
        self._max_attempts = max_attempts
        self._attempts: dict[tuple[str, str], int] = {}
        self.last_policy: EscalationPolicy | None = None
        self.replan_used: bool = False

    def total_attempts(self) -> int:
        return sum(self._attempts.values())

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
