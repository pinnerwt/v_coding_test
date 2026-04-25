from __future__ import annotations

from dataclasses import dataclass

from agent.locate import LocatorMiss

# ---------------------------------------------------------------------------
# Escalation table: (current_tier, miss_reason) -> next_tier
# Only L1 zero-match → L2 is implemented in this ticket.
# L2→L3, L3→L4, L1 ambiguous→L3 are future rows (see design.md).
# ---------------------------------------------------------------------------
_ESCALATION_TABLE: dict[tuple[str, str], str] = {
    ("L1_ax", "zero_matches"): "L2_dom",
}


@dataclass(frozen=True)
class EscalationDecision:
    """Immutable result returned by Supervisor.handle().

    Attributes:
        next_tier: The tier to try next ("L2_dom", "L3_rerank", "L4_vision"),
                   or None when the policy is "halt".
        policy:    "next_tier" or "halt".
        attempt:   The attempt count for this (tier, reason) strategy path.
    """

    next_tier: str | None
    policy: str
    attempt: int


class Supervisor:
    """Classifies a LocatorMiss and returns an escalation decision.

    One Supervisor instance should be created per task-run so that the
    per-strategy attempt counter is scoped correctly.

    Args:
        max_attempts: Maximum escalation attempts per (current_tier, reason)
                      strategy before halting. Defaults to 3.
    """

    def __init__(self, *, max_attempts: int = 3) -> None:
        self._max_attempts = max_attempts
        self._attempts: dict[tuple[str, str], int] = {}

    def handle(self, miss: LocatorMiss, *, current_tier: str) -> EscalationDecision:
        """Decide what to do given a LocatorMiss at the specified tier.

        Args:
            miss:         The LocatorMiss exception raised by the locator.
            current_tier: The tier that raised the miss (e.g. "L1_ax").

        Returns:
            EscalationDecision with next_tier and policy.
        """
        key = (current_tier, miss.reason)
        self._attempts[key] = self._attempts.get(key, 0) + 1
        attempt = self._attempts[key]

        if attempt > self._max_attempts:
            return EscalationDecision(next_tier=None, policy="halt", attempt=attempt)

        next_tier = _ESCALATION_TABLE.get(key)
        if next_tier is not None:
            return EscalationDecision(next_tier=next_tier, policy="next_tier", attempt=attempt)

        return EscalationDecision(next_tier=None, policy="halt", attempt=attempt)
