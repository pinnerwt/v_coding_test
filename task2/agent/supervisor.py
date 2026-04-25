from __future__ import annotations

from dataclasses import dataclass

from agent.locate import LocatorMiss

# Only implemented escalation row. L2→L3, L3→L4, and L1-ambiguous→L3 are
# deliberately absent so unknown (tier, reason) pairs fall through to halt.
_ESCALATION_TABLE: dict[tuple[str, str], str] = {
    ("L1_ax", "zero_matches"): "L2_dom",
}


@dataclass(frozen=True)
class EscalationDecision:
    next_tier: str | None
    policy: str
    attempt: int


class Supervisor:
    def __init__(self, *, max_attempts: int = 3) -> None:
        self._max_attempts = max_attempts
        self._attempts: dict[tuple[str, str], int] = {}

    def handle(self, miss: LocatorMiss, *, current_tier: str) -> EscalationDecision:
        key = (current_tier, miss.reason)
        attempt = self._attempts.get(key, 0) + 1
        self._attempts[key] = attempt

        if attempt > self._max_attempts:
            return EscalationDecision(next_tier=None, policy="halt", attempt=attempt)

        next_tier = _ESCALATION_TABLE.get(key)
        if next_tier is not None:
            return EscalationDecision(next_tier=next_tier, policy="next_tier", attempt=attempt)

        return EscalationDecision(next_tier=None, policy="halt", attempt=attempt)
