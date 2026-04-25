from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, get_args

if TYPE_CHECKING:
    from playwright.sync_api import Page

_SUPPORTED_ROLES: frozenset[str] = frozenset({"button", "link", "textbox", "checkbox", "heading"})
_ARTICLES: frozenset[str] = frozenset({"the", "a", "an"})

LocatorMissReason = Literal["zero_matches", "ambiguous"]
_VALID_REASONS: frozenset[str] = frozenset(get_args(LocatorMissReason))

_ACCESSIBLE_NAME_JS = """
(el) => {
  const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
  const labelledby = el.getAttribute('aria-labelledby');
  if (labelledby) {
    const parts = labelledby.split(/\\s+/).filter(Boolean).map((id) => {
      const ref = el.ownerDocument.getElementById(id);
      return ref ? norm(ref.textContent) : '';
    });
    const joined = norm(parts.join(' '));
    if (joined) return joined;
  }
  const ariaLabel = el.getAttribute('aria-label');
  if (ariaLabel) {
    const t = norm(ariaLabel);
    if (t) return t;
  }
  if (el.id) {
    const lbl = el.ownerDocument.querySelector('label[for="' + CSS.escape(el.id) + '"]');
    if (lbl) {
      const t = norm(lbl.textContent);
      if (t) return t;
    }
  }
  const wrapping = el.closest && el.closest('label');
  if (wrapping) {
    const t = norm(wrapping.textContent);
    if (t) return t;
  }
  const title = el.getAttribute('title');
  if (title) {
    const t = norm(title);
    if (t) return t;
  }
  return norm(el.textContent);
}
"""


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
            f"unknown role token {tokens[-1]!r} in intent {intent!r}; "
            f"supported: {sorted(_SUPPORTED_ROLES)}"
        )
    name_tokens = tokens[:-1]
    name = " ".join(name_tokens) if name_tokens else None
    return role, name


def locate_l1(page: Page, *, role: str, name: str | None) -> LocateResult:
    locator = page.get_by_role(role, name=name, exact=False) if name else page.get_by_role(role)
    count = locator.count()
    if count == 0:
        raise LocatorMiss(reason="zero_matches", match_count=0)
    if count > 1:
        raise LocatorMiss(reason="ambiguous", match_count=count)
    matched_name_raw = locator.first.evaluate(_ACCESSIBLE_NAME_JS)
    matched_name: str | None = matched_name_raw if isinstance(matched_name_raw, str) else None
    if name:
        escaped = name.replace("\\", "\\\\").replace('"', '\\"')
        selector = f'role={role}[name="{escaped}" i]'
    else:
        selector = f"role={role}"
    fingerprint_name = matched_name if matched_name is not None else (name or "")
    fingerprint = hashlib.sha256(f"{role}:{fingerprint_name}".encode()).hexdigest()
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
