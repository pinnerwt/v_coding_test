from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, get_args

if TYPE_CHECKING:
    from playwright.sync_api import Page

_SUPPORTED_ROLES: frozenset[str] = frozenset({"button", "link", "textbox", "checkbox", "heading"})
_ARTICLES: frozenset[str] = frozenset({"the", "a", "an"})

LocatorMissReason = Literal["zero_matches", "ambiguous", "vision_miss"]
_VALID_REASONS: frozenset[str] = frozenset(get_args(LocatorMissReason))

_L2_BUTTON_TAXONOMY_CSS = (
    "button, input[type=button], input[type=submit], input[type=reset], "
    '[role=button], [onclick], [class*="btn"], [class*="button"]'
)
_L2_LINK_TAXONOMY_CSS = "a[href], [role=link]"

_L3_MAX_CANDIDATES = 10
_L3_MAX_HEADING_CHARS = 100
_L3_MAX_NEARBY_CHARS = 200
_L3_CONFIDENCE = 0.8

_L4_CONFIDENCE = 0.5
_L4_DATA_URL_PREFIX = "data:image/png;base64,"
_L4_SYSTEM_PROMPT = (
    "You are a UI element localizer. Given a screenshot and an intent, return a "
    "single bounding box around the target element. Reply with EXACTLY the JSON "
    'object {"bbox": [x, y, w, h]} where x,y is the top-left corner in pixels '
    "(relative to the screenshot), and w,h are width and height in pixels. Do not "
    "wrap the JSON in code fences. Do not include any prose."
)


def _resolve_default_llm_chat() -> Callable[..., Any]:
    from agent.llm import chat

    return chat


def _escape_quoted(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _role_selector(role: str, name: str | None) -> str:
    if not name:
        return f"role={role}"
    return f'role={role}[name="{_escape_quoted(name)}" i]'


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
    coords: tuple[int, int] | None = None


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
    selector = _role_selector(role, name)
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


def locate_l2(page: Page, *, role: str, name: str | None) -> LocateResult:
    if not name:
        raise LocatorMiss(reason="zero_matches", match_count=0)

    if role == "textbox":
        strategy = "placeholder"
        locator = page.get_by_placeholder(name, exact=False)
        selector = f'[placeholder*="{_escape_quoted(name)}" i]'
    elif role in ("button", "link"):
        strategy = "text_contains"
        taxonomy = _L2_BUTTON_TAXONOMY_CSS if role == "button" else _L2_LINK_TAXONOMY_CSS
        locator = page.locator(taxonomy).filter(has_text=name)
        # filter(has_text=...) is substring + case-insensitive; mirror that with text=/.../i
        # so the stored selector re-resolves to the same node.
        pattern = re.escape(name).replace("/", r"\/")
        selector = f"{taxonomy} >> text=/{pattern}/i"
    else:
        raise LocatorMiss(reason="zero_matches", match_count=0)

    count = locator.count()
    if count == 1:
        fingerprint = hashlib.sha256(f"{role}:{name}:{strategy}".encode()).hexdigest()
        return LocateResult(
            tier="L2_dom",
            role=role,
            name=name,
            selector=selector,
            ax_fingerprint=fingerprint,
            confidence=0.7,
        )
    if count > 1:
        raise LocatorMiss(reason="ambiguous", match_count=count)
    raise LocatorMiss(reason="zero_matches", match_count=0)


_L3_CANDIDATE_CONTEXT_JS = """
(els, {headingChars, nearbyChars, maxCandidates}) => {
  const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
  const truncate = (s, n) => (s.length > n ? s.slice(0, n) : s);
  const accessibleName = __ACCESSIBLE_NAME__;

  const findHeading = (el) => {
    const section = el.closest && el.closest('section');
    if (section) {
      const aria = section.getAttribute('aria-label');
      if (aria) {
        const t = norm(aria);
        if (t) return t;
      }
      const inner = section.querySelector('h1, h2, h3, h4, h5, h6');
      if (inner) {
        const t = norm(inner.textContent);
        if (t) return t;
      }
    }
    let cur = el.previousElementSibling;
    while (cur) {
      if (/^H[1-6]$/.test(cur.tagName)) {
        const t = norm(cur.textContent);
        if (t) return t;
      }
      cur = cur.previousElementSibling;
    }
    let parent = el.parentElement;
    while (parent) {
      let sib = parent.previousElementSibling;
      while (sib) {
        if (/^H[1-6]$/.test(sib.tagName)) {
          const t = norm(sib.textContent);
          if (t) return t;
        }
        sib = sib.previousElementSibling;
      }
      parent = parent.parentElement;
    }
    return '';
  };

  const findNearby = (el) => {
    const container = el.closest && el.closest('section, article, nav, aside, main, form');
    const source = container || el.parentElement || el;
    return norm(source.textContent);
  };

  return els.slice(0, maxCandidates).map((el) => ({
    accessible_name: truncate(accessibleName(el), nearbyChars),
    section_heading: truncate(findHeading(el), headingChars),
    nearby_text: truncate(findNearby(el), nearbyChars),
  }));
}
""".strip().replace("__ACCESSIBLE_NAME__", _ACCESSIBLE_NAME_JS.strip())

_L3_CONTEXT_ARGS = {
    "headingChars": _L3_MAX_HEADING_CHARS,
    "nearbyChars": _L3_MAX_NEARBY_CHARS,
    "maxCandidates": _L3_MAX_CANDIDATES,
}


def _build_l3_messages(
    role: str,
    name: str | None,
    candidates: list[dict[str, str]],
) -> list[dict[str, str]]:
    intent = f"{name} {role}" if name else role
    lines = [
        f"Intent: {intent}",
        f"Candidate count: {len(candidates)}",
        "",
        "Candidates:",
    ]
    for i, c in enumerate(candidates):
        lines.append(
            f"[{i}] section={c['section_heading']!r} "
            f"text={c['accessible_name']!r} "
            f"nearby={c['nearby_text']!r}"
        )
    user_content = "\n".join(lines)
    system_content = (
        "You are a DOM disambiguator. Given a user intent and a numbered list of "
        "candidate elements, pick the candidate that best matches the intent. "
        'Reply with EXACTLY the JSON object {"index": N} where N is the integer '
        "index of the chosen candidate. Do not wrap the JSON in code fences. "
        "Do not include any prose."
    )
    return [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_content},
    ]


def locate_l3(
    page: Page,
    *,
    role: str,
    name: str | None,
    llm_chat: Callable[..., Any] | None = None,
) -> LocateResult:
    locator = page.get_by_role(role, name=name, exact=False) if name else page.get_by_role(role)
    count = locator.count()
    if count == 0:
        raise LocatorMiss(reason="zero_matches", match_count=0)

    candidates = locator.evaluate_all(_L3_CANDIDATE_CONTEXT_JS, _L3_CONTEXT_ARGS)

    if len(candidates) == 1:
        chosen = 0
    else:
        from agent.llm import LLMError

        chat_fn = llm_chat if llm_chat is not None else _resolve_default_llm_chat()
        try:
            response = chat_fn(messages=_build_l3_messages(role, name, candidates), temperature=0.0)
        except LLMError as exc:
            raise LocatorMiss(reason="ambiguous", match_count=count) from exc
        idx = _parse_l3_index(response, len(candidates))
        if idx is None:
            raise LocatorMiss(reason="ambiguous", match_count=count)
        chosen = idx

    selector = f"{_role_selector(role, name)} >> nth={chosen}"
    section_heading = candidates[chosen]["section_heading"]
    fingerprint = hashlib.sha256(f"{role}:{name or ''}:{section_heading}".encode()).hexdigest()
    return LocateResult(
        tier="L3_rerank",
        role=role,
        name=name,
        selector=selector,
        ax_fingerprint=fingerprint,
        confidence=_L3_CONFIDENCE,
    )


def _parse_l3_index(response: Any, candidate_count: int) -> int | None:
    content = getattr(response, "content", None)
    if not isinstance(content, str):
        return None
    try:
        data = json.loads(content)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    idx = data.get("index")
    if isinstance(idx, bool) or not isinstance(idx, int):
        return None
    if not 0 <= idx < candidate_count:
        return None
    return idx


def _build_l4_messages(
    intent: str,
    viewport: tuple[int, int],
    png_b64: str,
) -> list[dict[str, Any]]:
    vw, vh = viewport
    return [
        {"role": "system", "content": _L4_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": f"Intent: {intent}\nViewport: {vw}x{vh}"},
                {
                    "type": "image_url",
                    "image_url": {"url": f"{_L4_DATA_URL_PREFIX}{png_b64}"},
                },
            ],
        },
    ]


def _parse_l4_bbox(
    response: Any,
    viewport_w: int,
    viewport_h: int,
) -> tuple[int, int] | None:
    content = getattr(response, "content", None)
    if not isinstance(content, str):
        return None
    try:
        data = json.loads(content)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    bbox = data.get("bbox")
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 4:
        return None
    norm: list[int] = []
    for v in bbox:
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return None
        if not math.isfinite(v):
            return None
        norm.append(int(round(v)))
    x, y, w, h = norm
    if x < 0 or y < 0 or w <= 0 or h <= 0:
        return None
    if x + w > viewport_w or y + h > viewport_h:
        return None
    return (x + w // 2, y + h // 2)


def locate_l4(
    page: Page,
    *,
    role: str,
    name: str | None,
    intent: str,
    llm_chat: Callable[..., Any] | None = None,
) -> LocateResult:
    vp = page.viewport_size
    if vp is None:
        raise LocatorMiss(reason="vision_miss", match_count=0)

    png_bytes = page.screenshot(full_page=False)
    png_b64 = base64.b64encode(png_bytes).decode("ascii")

    chat_fn = llm_chat if llm_chat is not None else _resolve_default_llm_chat()
    messages = _build_l4_messages(intent, (vp["width"], vp["height"]), png_b64)

    from agent.llm import LLMError

    try:
        response = chat_fn(messages=messages, temperature=0.0)
    except LLMError as exc:
        raise LocatorMiss(reason="vision_miss", match_count=0) from exc

    center = _parse_l4_bbox(response, vp["width"], vp["height"])
    if center is None:
        raise LocatorMiss(reason="vision_miss", match_count=0)
    cx, cy = center

    fingerprint = hashlib.sha256(f"vision:{intent}:{cx}:{cy}".encode()).hexdigest()
    return LocateResult(
        tier="L4_vision",
        role=role,
        name=name,
        selector="",
        ax_fingerprint=fingerprint,
        confidence=_L4_CONFIDENCE,
        coords=(cx, cy),
    )


def locate(
    page: Page,
    intent: str,
    *,
    llm_chat: Callable[..., Any] | None = None,
) -> LocateResult:
    role, name = parse_intent(intent)
    try:
        return locate_l1(page, role=role, name=name)
    except LocatorMiss as miss:
        if miss.reason == "zero_matches":
            try:
                return locate_l2(page, role=role, name=name)
            except LocatorMiss:
                return locate_l4(page, role=role, name=name, intent=intent, llm_chat=llm_chat)
        if miss.reason == "ambiguous":
            try:
                return locate_l3(page, role=role, name=name, llm_chat=llm_chat)
            except LocatorMiss:
                return locate_l4(page, role=role, name=name, intent=intent, llm_chat=llm_chat)
        raise
