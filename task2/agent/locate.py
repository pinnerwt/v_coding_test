from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from playwright.sync_api import Page

_SUPPORTED_ROLES: frozenset[str] = frozenset({"button", "link", "textbox", "checkbox", "heading"})
_ARTICLES: frozenset[str] = frozenset({"the", "a", "an"})

LocatorMissReason = Literal["zero_matches", "ambiguous"]
_VALID_REASONS: frozenset[str] = frozenset({"zero_matches", "ambiguous"})


class LocateError(Exception):
    pass


class IntentParseError(LocateError):
    pass


class LocatorMiss(LocateError):
    def __init__(self, *, reason: str, match_count: int):
        if reason not in _VALID_REASONS:
            raise ValueError(f"reason must be one of {sorted(_VALID_REASONS)}, got {reason!r}")
        self.reason: LocatorMissReason = reason  # type: ignore[assignment]
        self.match_count = match_count
        super().__init__(f"locator miss: {reason} (match_count={match_count})")


@dataclass(frozen=True)
class LocateResult:
    tier: str
    role: str
    name: str | None
    selector: str
    ax_fingerprint: str
    confidence: float


def parse_intent(intent: str) -> tuple[str, str | None]:
    tokens = intent.split()
    if not tokens:
        raise IntentParseError("intent is empty")
    if len(tokens) > 1 and tokens[0].lower() in _ARTICLES:
        tokens = tokens[1:]
    role = tokens[-1].lower()
    if role not in _SUPPORTED_ROLES:
        raise IntentParseError(
            f"unknown role token {tokens[-1]!r}; supported: {sorted(_SUPPORTED_ROLES)}"
        )
    name_tokens = tokens[:-1]
    name = " ".join(name_tokens) if name_tokens else None
    return role, name


def locate_l1(page: Page, *, role: str, name: str | None) -> LocateResult:
    locator = page.get_by_role(role, name=name) if name else page.get_by_role(role)
    count = locator.count()
    if count == 0:
        raise LocatorMiss(reason="zero_matches", match_count=0)
    if count > 1:
        raise LocatorMiss(reason="ambiguous", match_count=count)
    selector = f'role={role}[name="{name}" i]' if name else f"role={role}"
    fingerprint = hashlib.sha256(f"{role}:{name or ''}".encode()).hexdigest()
    return LocateResult(
        tier="L1_ax",
        role=role,
        name=name,
        selector=selector,
        ax_fingerprint=fingerprint,
        confidence=1.0,
    )


def locate(page: Page, intent: str) -> LocateResult:
    role, name = parse_intent(intent)
    return locate_l1(page, role=role, name=name)
