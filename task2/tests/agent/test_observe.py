from __future__ import annotations

import base64
import re

import pytest

from agent.browser import Browser
from agent.observe import MAX_NODES, build_observation
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
    button_lines = [l for l in lines if l.startswith("[button]")]
    assert len(button_lines) == MAX_NODES
    last = lines[-1]
    assert re.match(r"\[\.\.\. \d+ more nodes truncated\]", last), f"Unexpected last line: {last!r}"


def test_last_action_none_first_step(browser_on_mixed):
    obs = build_observation(browser_on_mixed, None)
    assert "last_action" in obs
    assert obs["last_action"] is None


def test_last_action_threaded_second_step(browser_on_mixed):
    action = {"tool": "goto", "intent": "navigate", "outcome": "ok"}
    obs = build_observation(browser_on_mixed, action)
    assert obs["last_action"] == action


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
