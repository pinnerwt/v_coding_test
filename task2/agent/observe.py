from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.browser import Browser

INTERACTABLE_ROLES: frozenset[str] = frozenset(
    {
        "button",
        "link",
        "textbox",
        "combobox",
        "checkbox",
        "radio",
        "tab",
        "menuitem",
        "option",
        "heading",
    }
)

MAX_NODES: int = 200
MAX_NAME_LEN: int = 80

_EMPTY_FINGERPRINT: str = hashlib.sha256(b"").hexdigest()

# T5: keywords that mark a transient toast/notification line in the AX-tree
# digest. A diff containing only such lines (no removals, ≤2 additions) is
# classified as "minor: notification appeared" so the agent doesn't mistake
# a passive toast for evidence of user-driven state change.
_NOTIFICATION_KEYWORDS: tuple[str, ...] = (
    "alert",
    "notification",
    "status",
    "toast",
)


def _line_is_notification(line: str) -> bool:
    lowered = line.lower()
    return any(kw in lowered for kw in _NOTIFICATION_KEYWORDS)


def compute_dom_digest(prev_obs: dict | None, curr_obs: dict) -> str:
    """Return a short verbal summary of how `curr_obs` differs from `prev_obs`.

    Output vocabulary:
      - ""                              — no prior observation
      - "unchanged"                     — same URL and same ax_fingerprint
      - "url_changed: <prev> → <curr>"  — URL transitioned (takes priority)
      - "minor: notification appeared"  — only added a toast/alert line
      - "minor: N node(s) added"        — small additions, no removals
      - "changed: +A -R"                — general change
    """
    if prev_obs is None:
        return ""
    prev_url = prev_obs.get("url") or ""
    curr_url = curr_obs.get("url") or ""
    if prev_url != curr_url:
        return f"url_changed: {prev_url} → {curr_url}"
    if prev_obs.get("ax_fingerprint") == curr_obs.get("ax_fingerprint"):
        return "unchanged"
    prev_lines = set((prev_obs.get("ax_tree_digest") or "").splitlines())
    curr_lines = set((curr_obs.get("ax_tree_digest") or "").splitlines())
    added = curr_lines - prev_lines
    removed = prev_lines - curr_lines
    if not removed and added and len(added) <= 2 and any(_line_is_notification(ln) for ln in added):
        return "minor: notification appeared"
    if not removed and added and len(added) <= 3:
        return f"minor: {len(added)} node(s) added"
    return f"changed: +{len(added)} -{len(removed)}"


def _detach_silently(session) -> None:
    try:
        session.detach()
    except Exception:  # noqa: BLE001
        pass


def _ax_nodes(browser) -> tuple[list[dict], int]:
    page = browser._page
    sessions = browser._cdp_sessions

    cdp = sessions.get(id(page))
    if cdp is None:
        for stale in sessions.values():
            _detach_silently(stale)
        sessions.clear()
        try:
            cdp = page.context.new_cdp_session(page)
        except Exception:  # noqa: BLE001
            return [], 0
        sessions[id(page)] = cdp

    try:
        result = cdp.send("Accessibility.getFullAXTree")
    except Exception:  # noqa: BLE001
        _detach_silently(cdp)
        sessions.pop(id(page), None)
        return [], 0

    out: list[dict] = []
    total = 0
    for n in result.get("nodes", []):
        role = n.get("role", {}).get("value", "")
        if role not in INTERACTABLE_ROLES:
            continue
        total += 1
        if len(out) >= MAX_NODES:
            continue
        name = n.get("name", {}).get("value", "") or ""
        node: dict = {"role": role, "name": name}
        if role == "heading":
            for p in n.get("properties", []):
                if p.get("name") == "level":
                    level = p.get("value", {}).get("value")
                    if level is not None:
                        node["level"] = level
                    break
        out.append(node)
    return out, total


def _serialize(nodes: list[dict], total_found: int) -> str:
    lines: list[str] = []
    for node in nodes:
        name: str = node.get("name") or ""
        if len(name) > MAX_NAME_LEN:
            name = name[:MAX_NAME_LEN] + "…"
        if "level" in node:
            label = f"[heading:{node['level']}]"
        else:
            label = f"[{node['role']}]"
        lines.append(f'{label} "{name}"')
    if total_found > MAX_NODES:
        lines.append(f"[... {total_found - MAX_NODES} more nodes truncated]")
    return "\n".join(lines)


def build_observation(browser: Browser, last_actions: list[dict]) -> dict:
    page = browser._page
    if page is None:
        return {
            "url": "",
            "title": "",
            "ax_tree_digest": "",
            "ax_fingerprint": _EMPTY_FINGERPRINT,
            "last_actions": last_actions,
        }

    capped, total_found = _ax_nodes(browser)
    ax_tree_digest = _serialize(capped, total_found)
    ax_fingerprint = hashlib.sha256(ax_tree_digest.encode()).hexdigest()

    return {
        "url": page.url,
        "title": page.title(),
        "ax_tree_digest": ax_tree_digest,
        "ax_fingerprint": ax_fingerprint,
        "last_actions": last_actions,
    }
