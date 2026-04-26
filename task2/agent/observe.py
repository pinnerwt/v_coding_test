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


def _ax_nodes(page) -> list[dict]:
    try:
        ctx = page.context
        cdp = ctx.new_cdp_session(page)
    except AttributeError:
        return []
    try:
        result = cdp.send("Accessibility.getFullAXTree")
    except Exception:  # noqa: BLE001
        return []
    finally:
        try:
            cdp.detach()
        except Exception:  # noqa: BLE001
            pass
    raw = result.get("nodes", [])
    out: list[dict] = []
    for n in raw:
        role = n.get("role", {}).get("value", "")
        if role not in INTERACTABLE_ROLES:
            continue
        name = n.get("name", {}).get("value", "") or ""
        props = {p["name"]: p.get("value", {}).get("value") for p in n.get("properties", [])}
        node: dict = {"role": role, "name": name}
        if role == "heading" and props.get("level") is not None:
            node["level"] = props["level"]
        out.append(node)
    return out


def _serialize(nodes: list[dict], total_found: int) -> str:
    lines: list[str] = []
    for node in nodes:
        role = node["role"]
        name: str = node.get("name") or ""
        if len(name) > MAX_NAME_LEN:
            name = name[:MAX_NAME_LEN] + "…"
        if role == "heading" and "level" in node:
            label = f"[heading:{node['level']}]"
        else:
            label = f"[{role}]"
        lines.append(f'{label} "{name}"')
    if total_found > MAX_NODES:
        lines.append(f"[... {total_found - MAX_NODES} more nodes truncated]")
    return "\n".join(lines)


def build_observation(browser: Browser, last_action: dict | None) -> dict:
    page = browser._page
    if page is None:
        empty_digest = ""
        return {
            "url": "",
            "title": "",
            "ax_tree_digest": empty_digest,
            "ax_fingerprint": hashlib.sha256(empty_digest.encode()).hexdigest(),
            "last_action": last_action,
        }

    all_nodes = _ax_nodes(page)
    total_found = len(all_nodes)
    capped = all_nodes[:MAX_NODES]

    ax_tree_digest = _serialize(capped, total_found)
    ax_fingerprint = hashlib.sha256(ax_tree_digest.encode()).hexdigest()

    return {
        "url": page.url,
        "title": page.title(),
        "ax_tree_digest": ax_tree_digest,
        "ax_fingerprint": ax_fingerprint,
        "last_action": last_action,
    }
