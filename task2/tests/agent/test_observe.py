from __future__ import annotations

import base64
import re

import pytest

from agent.browser import Browser
from agent.observe import INTERACTABLE_ROLES, MAX_NAME_LEN, MAX_NODES, build_observation
from agent.trace import ObservationEvent


@pytest.fixture
def browser_on_mixed(fixture_server, playwright_chromium):
    url = f"{fixture_server}/observe_mixed.html"
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(url)
        yield b


def test_decorative_divs_excluded_buttons_included(browser_on_mixed):
    obs = build_observation(browser_on_mixed, None)
    digest = obs["ax_tree_digest"]
    assert "[button]" in digest
    assert "generic" not in digest
    assert not re.search(r"\bdiv\b", digest)


def test_1000_button_page_capped(playwright_chromium):
    buttons_html = "".join(f"<button>btn{i}</button>" for i in range(1000))
    html = f"<!DOCTYPE html><html><body>{buttons_html}</body></html>"
    encoded = base64.b64encode(html.encode()).decode()
    data_url = f"data:text/html;base64,{encoded}"

    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(data_url)
        obs = build_observation(b, None)

    digest = obs["ax_tree_digest"]
    lines = digest.splitlines()
    button_lines = [ln for ln in lines if ln.startswith("[button]")]
    assert len(button_lines) == MAX_NODES
    last = lines[-1]
    assert re.match(r"\[\.\.\. \d+ more nodes truncated\]", last), f"Unexpected last line: {last!r}"
    sentinel_count = int(re.search(r"\d+", last).group())
    assert sentinel_count == 1000 - MAX_NODES


def test_last_action_none_first_step(browser_on_mixed):
    obs = build_observation(browser_on_mixed, None)
    assert "last_action" in obs
    assert obs["last_action"] is None


def test_last_action_threaded_second_step(browser_on_mixed):
    action = {"tool": "goto", "intent": "navigate", "outcome": "ok"}
    obs = build_observation(browser_on_mixed, action)
    assert obs["last_action"] == action


def test_build_observation_closed_browser_returns_valid_dict(playwright_chromium):
    """build_observation with page=None returns zero-observation without raising."""
    with Browser(playwright_browser=playwright_chromium) as b:
        pass
    obs = build_observation(b, None)
    assert obs["url"] == ""
    assert obs["title"] == ""
    assert obs["ax_tree_digest"] == ""
    assert obs["ax_fingerprint"] != ""
    assert obs["last_action"] is None


def test_ax_tree_digest_round_trips_through_trace(browser_on_mixed):
    obs = build_observation(browser_on_mixed, None)
    ax_tree_digest = obs["ax_tree_digest"]
    ax_fingerprint = obs["ax_fingerprint"]

    event = ObservationEvent(
        run_id="test-run",
        seq=1,
        ts="2026-01-01T00:00:00Z",
        step_id="step-1",
        kind="observation",
        url=obs["url"],
        title=obs["title"],
        ax_tree_digest=ax_tree_digest,
        ax_fingerprint=ax_fingerprint,
        screenshot_ref="",
        viewport={},
    )

    json_str = event.model_dump_json()
    restored = ObservationEvent.model_validate_json(json_str)
    assert restored.ax_tree_digest == ax_tree_digest
    assert restored.ax_fingerprint == ax_fingerprint


def test_interactable_roles_is_frozenset_with_canonical_set():
    assert isinstance(INTERACTABLE_ROLES, frozenset)
    assert INTERACTABLE_ROLES == {
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


def test_links_and_headings_included(browser_on_mixed):
    obs = build_observation(browser_on_mixed, None)
    digest = obs["ax_tree_digest"]
    assert "[heading" in digest
    assert "[link]" in digest


def test_heading_level_in_serialization(fixture_server, playwright_chromium):
    html = "<!DOCTYPE html><html><body><h2>My Heading</h2></body></html>"
    encoded = base64.b64encode(html.encode()).decode()
    data_url = f"data:text/html;base64,{encoded}"
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(data_url)
        obs = build_observation(b, None)
    assert '[heading:2] "My Heading"' in obs["ax_tree_digest"]


def test_long_name_truncated_to_max_name_len(fixture_server, playwright_chromium):
    long_name = "x" * 200
    html = f"<!DOCTYPE html><html><body><button>{long_name}</button></body></html>"
    encoded = base64.b64encode(html.encode()).decode()
    data_url = f"data:text/html;base64,{encoded}"
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(data_url)
        obs = build_observation(b, None)
    digest = obs["ax_tree_digest"]
    line = next(ln for ln in digest.splitlines() if ln.startswith("[button]"))
    quoted_name = line[len('[button] "') : -1]
    assert quoted_name.endswith("…")
    assert len(quoted_name) == MAX_NAME_LEN + 1


def test_fingerprint_is_deterministic(browser_on_mixed):
    obs1 = build_observation(browser_on_mixed, None)
    obs2 = build_observation(browser_on_mixed, None)
    assert obs1["ax_fingerprint"] == obs2["ax_fingerprint"]


def test_fingerprint_changes_when_dom_changes(fixture_server, playwright_chromium):
    html = "<!DOCTYPE html><html><body><button>Original</button></body></html>"
    encoded = base64.b64encode(html.encode()).decode()
    data_url = f"data:text/html;base64,{encoded}"
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(data_url)
        fp1 = build_observation(b, None)["ax_fingerprint"]
        b._page.evaluate(
            "() => {"
            " const btn = document.createElement('button');"
            " btn.textContent = 'New';"
            " document.body.appendChild(btn);"
            " }"
        )
        fp2 = build_observation(b, None)["ax_fingerprint"]
    assert fp1 != fp2
