from __future__ import annotations

import base64
import hashlib
import json
import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, get_args

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from agent.locator_cache import LocatorCache

SupportedRole = Literal["button", "link", "textbox", "checkbox", "heading", "list", "listitem"]
_SUPPORTED_ROLES: frozenset[str] = frozenset(get_args(SupportedRole))
# F22: combobox is a textbox-shaped role at the locator level (F13 added the
# alias inside `_l1_roles_to_try`); accept it at parse_intent so the agent
# doesn't self-disqualify on `intent="X combobox"`.
_ROLE_ALIASES: dict[str, str] = {
    "items": "listitem",
    "lists": "list",
    "combobox": "textbox",
}
_ARTICLES: frozenset[str] = frozenset({"the", "a", "an"})
# Punctuation stripped from each token before role-matching. The LLM commonly
# emits intents like `'the combobox labeled "搜尋 Google 地圖"'`, where the
# closing `"` attaches to the last whitespace-token and turns the role lookup
# into `'地圖"'` — guaranteed parse error. Strip these so the role becomes
# recognizable wherever it sits in the phrase.
_TOKEN_TRIM_CHARS = "\"'`,.;:!?()[]{}<>"
# Tokens that, when they appear immediately after the role, signal that the
# rest of the phrase is the accessible name. e.g. `'X labeled Y'` → name=Y.
_NAME_HINT_TOKENS: frozenset[str] = frozenset(
    {"labeled", "named", "label", "placeholder", "called", "titled"}
)

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
    # F15: when L1 returns a role-only singleton because the name filter
    # missed (typically: page accessible name is in a different language
    # than the agent's intent token), this is "role_singleton". None means
    # the result was a normal name-matched hit.
    name_fallback: str | None = None


def parse_intent(intent: str) -> tuple[str, str | None]:
    raw_tokens = intent.split()
    if not raw_tokens:
        raise IntentParseError("intent is empty")
    cleaned = [t.strip(_TOKEN_TRIM_CHARS) for t in raw_tokens]
    cleaned = [c for c in cleaned if c]
    if not cleaned:
        raise IntentParseError(f"intent {intent!r} is empty after stripping punctuation")
    if len(cleaned) > 1 and cleaned[0].lower() in _ARTICLES:
        cleaned = cleaned[1:]
    role: str | None = None
    role_idx: int | None = None
    for idx in range(len(cleaned) - 1, -1, -1):
        candidate = cleaned[idx].lower()
        candidate = _ROLE_ALIASES.get(candidate, candidate)
        if candidate in _SUPPORTED_ROLES:
            role = candidate
            role_idx = idx
            break
    if role is None or role_idx is None:
        raise IntentParseError(
            f"no supported role token in intent {intent!r}; "
            f"supported: {sorted(_SUPPORTED_ROLES | _ROLE_ALIASES.keys())}"
        )
    after = cleaned[role_idx + 1 :]
    name: str | None = None
    if after:
        i = 0
        while i < len(after) and after[i].lower() == "with":
            i += 1
        if i < len(after) and after[i].lower() in _NAME_HINT_TOKENS:
            name_tokens_after = after[i + 1 :]
            if name_tokens_after:
                name = " ".join(name_tokens_after)
    if name is None:
        before = cleaned[:role_idx]
        name = " ".join(before) if before else None
    return role, name


# F13: textbox-shaped intents must also match `role=combobox` inputs. Sites
# like google.com and Google Maps render their search input as a combobox
# (per ARIA combobox-with-listbox pattern), so a `role=textbox` query alone
# misses the only entry point on the page.
_TEXTBOX_ROLE_ALIASES: tuple[str, ...] = ("textbox", "combobox")


def _l1_roles_to_try(role: str) -> tuple[str, ...]:
    if role == "textbox":
        return _TEXTBOX_ROLE_ALIASES
    return (role,)


_L1_ROLE_SINGLETON_CONFIDENCE = 0.7


def locate_l1(page: Page, *, role: str, name: str | None) -> LocateResult:
    last_miss: LocatorMiss | None = None
    for try_role in _l1_roles_to_try(role):
        locator = (
            page.get_by_role(try_role, name=name, exact=False)
            if name
            else page.get_by_role(try_role)
        )
        count = locator.count()
        if count == 0:
            last_miss = LocatorMiss(reason="zero_matches", match_count=0)
            continue
        if count > 1:
            last_miss = LocatorMiss(reason="ambiguous", match_count=count)
            continue
        matched_name_raw = locator.first.evaluate(_ACCESSIBLE_NAME_JS)
        matched_name: str | None = matched_name_raw if isinstance(matched_name_raw, str) else None
        selector = _role_selector(try_role, name)
        fingerprint_name = matched_name if matched_name is not None else (name or "")
        fingerprint = hashlib.sha256(f"{try_role}:{fingerprint_name}".encode()).hexdigest()
        return LocateResult(
            tier="L1_ax",
            role=try_role,
            name=name,
            selector=selector,
            ax_fingerprint=fingerprint,
            confidence=1.0,
        )
    # F15: name-filtered match missed across every role alias. Try the union
    # of role aliases without the name filter — if exactly one element on the
    # page carries any of those roles, return it as a role-singleton fallback.
    # This unblocks pages whose accessible name is in a different language
    # than the agent's intent token (page-shape rule, not locale-specific).
    if name:
        singleton = _l1_role_only_singleton(page, role)
        if singleton is not None:
            try_role, locator = singleton
            matched_name_raw = locator.evaluate(_ACCESSIBLE_NAME_JS)
            matched_name = matched_name_raw if isinstance(matched_name_raw, str) else ""
            selector = _role_selector(try_role, None)
            fingerprint = hashlib.sha256(f"{try_role}:{matched_name}".encode()).hexdigest()
            return LocateResult(
                tier="L1_ax",
                role=try_role,
                name=name,
                selector=selector,
                ax_fingerprint=fingerprint,
                confidence=_L1_ROLE_SINGLETON_CONFIDENCE,
                name_fallback="role_singleton",
            )
    assert last_miss is not None  # at least one role tried
    raise last_miss


def _l1_role_only_singleton(page: Page, role: str) -> tuple[str, Any] | None:
    """Return (role, locator-of-the-one-element) if the union of role aliases
    has exactly one matching element on the page. Otherwise None."""
    matches: list[tuple[str, Any]] = []
    total = 0
    for try_role in _l1_roles_to_try(role):
        locator = page.get_by_role(try_role)
        c = locator.count()
        total += c
        if c == 1:
            matches.append((try_role, locator.first))
        elif c > 1:
            return None
    if total != 1 or len(matches) != 1:
        return None
    return matches[0]


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

    png_bytes = page.screenshot(full_page=False, scale="css")
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


# F8: clickable-ish element shortlist for verbatim text-substring fallback.
# Used as a final tier before L4_vision when L1/L2 miss and the intent name
# (often non-ASCII) does not match any role-typed candidate. Matches the
# innermost element whose textContent contains `name` verbatim, biased to
# clickable surfaces so we do not return raw <p> / <span> blobs.
_L_TEXTMATCH_CSS = (
    "a[href], button, input[type=button], input[type=submit], input[type=reset], "
    "[role=button], [role=link], [onclick], [tabindex], "
    '[class*="btn"], [class*="button"], [class*="link"], [class*="cta"]'
)
_L_TEXTMATCH_CONFIDENCE = 0.6


def locate_l_textmatch(page: Page, *, role: str, name: str | None) -> LocateResult:
    """Last-resort tier: match clickable-ish elements whose textContent
    contains `name` verbatim. Role-agnostic — primarily for non-English
    DOM where AX-name matching fails (e.g. `<div onclick>網路訂位</div>`)."""
    if not name:
        raise LocatorMiss(reason="zero_matches", match_count=0)
    locator = page.locator(_L_TEXTMATCH_CSS).filter(has_text=name)
    count = locator.count()
    if count == 0:
        raise LocatorMiss(reason="zero_matches", match_count=0)
    # If multiple match, prefer the element with the shortest textContent
    # (most specific / innermost). Index resolution is deterministic so the
    # selector round-trips through canonical fingerprint revalidation.
    if count > 1:
        lengths = locator.evaluate_all(
            "els => els.map(e => (e.textContent || '').replace(/\\s+/g, ' ').trim().length)"
        )
        chosen = min(range(len(lengths)), key=lambda i: lengths[i])
    else:
        chosen = 0
    pattern = re.escape(name).replace("/", r"\/")
    selector = f"{_L_TEXTMATCH_CSS} >> text=/{pattern}/i >> nth={chosen}"
    fingerprint = hashlib.sha256(f"{role}:{name}:textmatch".encode()).hexdigest()
    return LocateResult(
        tier="L_textmatch",
        role=role,
        name=name,
        selector=selector,
        ax_fingerprint=fingerprint,
        confidence=_L_TEXTMATCH_CONFIDENCE,
    )


def _canonical_ax_fingerprint(page: Page, *, role: str, selector: str) -> str | None:
    # Single revalidation rule for the locator cache: hash role:accessible_name of
    # the element the selector resolves to. Returns None when the selector does not
    # resolve to exactly one element — zero matches and ambiguous matches both
    # invalidate the cache so the ladder gets a fresh shot at L1/L3 disambiguation.
    names = page.locator(selector).evaluate_all(f"els => els.map({_ACCESSIBLE_NAME_JS})")
    if len(names) != 1:
        return None
    accessible_name = names[0] if isinstance(names[0], str) else ""
    return hashlib.sha256(f"{role}:{accessible_name}".encode()).hexdigest()


def _resolve_via_ladder(
    page: Page,
    *,
    role: str,
    name: str | None,
    intent: str,
    llm_chat: Callable[..., Any] | None,
    on_event: Callable[[dict], None] | None = None,
) -> LocateResult:
    def _emit(payload: dict) -> None:
        if on_event is not None:
            on_event(payload)

    def _hit(result: LocateResult) -> LocateResult:
        _emit(
            {
                "tier": result.tier,
                "outcome": "hit",
                "chosen": {"role": result.role, "selector": result.selector},
            }
        )
        return result

    try:
        return _hit(locate_l1(page, role=role, name=name))
    except LocatorMiss as miss:
        _emit({"tier": "L1_ax", "outcome": miss.reason, "miss": miss})
        if miss.reason == "zero_matches":
            try:
                return _hit(locate_l2(page, role=role, name=name))
            except LocatorMiss as l2_miss:
                _emit({"tier": "L2_dom", "outcome": l2_miss.reason, "miss": l2_miss})
                # F8: try verbatim textContent substring match against
                # clickable-ish elements before falling back to vision.
                try:
                    return _hit(locate_l_textmatch(page, role=role, name=name))
                except LocatorMiss as tm_miss:
                    _emit({"tier": "L_textmatch", "outcome": tm_miss.reason, "miss": tm_miss})
                    if llm_chat is None:
                        raise
                    try:
                        return _hit(
                            locate_l4(page, role=role, name=name, intent=intent, llm_chat=llm_chat)
                        )
                    except LocatorMiss as l4_miss:
                        _emit({"tier": "L4_vision", "outcome": l4_miss.reason, "miss": l4_miss})
                        raise
        if miss.reason == "ambiguous":
            if llm_chat is None:
                raise
            try:
                return _hit(locate_l3(page, role=role, name=name, llm_chat=llm_chat))
            except LocatorMiss as l3_miss:
                _emit({"tier": "L3_rerank", "outcome": l3_miss.reason, "miss": l3_miss})
                try:
                    return _hit(
                        locate_l4(page, role=role, name=name, intent=intent, llm_chat=llm_chat)
                    )
                except LocatorMiss as l4_miss:
                    _emit({"tier": "L4_vision", "outcome": l4_miss.reason, "miss": l4_miss})
                    raise
        raise


def locate(
    page: Page,
    intent: str,
    *,
    llm_chat: Callable[..., Any] | None = None,
    cache: LocatorCache | None = None,
    on_event: Callable[[dict], None] | None = None,
) -> LocateResult:
    def _emit(payload: dict) -> None:
        if on_event is not None:
            on_event(payload)

    role, name = parse_intent(intent)

    origin: str | None = None
    if cache is not None:
        from agent.locator_cache import CacheEntry, _origin_from_url

        origin = _origin_from_url(page.url)
        entry = cache.get(origin=origin, intent=intent)
        if entry is not None:
            if entry.tier == "L4_vision":
                cache.invalidate(origin=origin, intent=intent)
                _emit({"tier": "cache", "outcome": "miss", "cache_action": "invalidate"})
            else:
                live_fp = _canonical_ax_fingerprint(page, role=entry.role, selector=entry.selector)
                if live_fp is None or live_fp != entry.ax_fingerprint:
                    cache.invalidate(origin=origin, intent=intent)
                    _emit({"tier": "cache", "outcome": "miss", "cache_action": "invalidate"})
                else:
                    _emit(
                        {
                            "tier": "cache",
                            "outcome": "hit",
                            "cache_action": "read",
                            "chosen": {
                                "role": entry.role,
                                "selector": entry.selector,
                                "ax_fingerprint": entry.ax_fingerprint,
                            },
                        }
                    )
                    return LocateResult(
                        tier="cache",
                        role=entry.role,
                        name=entry.name,
                        selector=entry.selector,
                        ax_fingerprint=entry.ax_fingerprint,
                        confidence=entry.confidence,
                        coords=entry.coords,
                    )

    result = _resolve_via_ladder(
        page, role=role, name=name, intent=intent, llm_chat=llm_chat, on_event=on_event
    )

    if cache is not None and origin is not None:
        if result.tier == "L4_vision":
            stored_fingerprint = result.ax_fingerprint
        else:
            canonical = _canonical_ax_fingerprint(page, role=result.role, selector=result.selector)
            stored_fingerprint = canonical if canonical is not None else result.ax_fingerprint
        written_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        cache.put(
            CacheEntry(
                origin=origin,
                intent=intent,
                role=result.role,
                name=result.name,
                selector=result.selector,
                ax_fingerprint=stored_fingerprint,
                confidence=result.confidence,
                tier=result.tier,
                coords=result.coords,
                written_at_utc=written_at,
            )
        )
        _emit(
            {
                "tier": result.tier,
                "outcome": "cache_write",
                "cache_action": "write",
                "chosen": {
                    "role": result.role,
                    "selector": result.selector,
                    "ax_fingerprint": stored_fingerprint,
                },
            }
        )

    return result
