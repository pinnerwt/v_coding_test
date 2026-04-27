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
