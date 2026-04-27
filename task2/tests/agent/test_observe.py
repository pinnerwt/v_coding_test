from __future__ import annotations

import base64
import re
import types
import unittest.mock

import pytest

from agent.browser import Browser
from agent.observe import (
    _EMPTY_FINGERPRINT,
    INTERACTABLE_ROLES,
    MAX_NAME_LEN,
    MAX_NODES,
    build_observation,
)
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
    assert len(obs["ax_fingerprint"]) == 64
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


def test_build_observation_falls_back_when_new_cdp_session_raises():
    # Firefox/WebKit lack CDP; observe must still produce a usable observation.
    def _raise(page):
        raise RuntimeError("CDP unsupported on this browser")

    fake_context = types.SimpleNamespace(new_cdp_session=_raise)
    fake_page = types.SimpleNamespace(
        url="http://example.com/",
        title=lambda: "Example",
        context=fake_context,
    )
    fake_browser = types.SimpleNamespace(_page=fake_page, _cdp_sessions={})

    obs = build_observation(fake_browser, None)

    assert obs["url"] == "http://example.com/"
    assert obs["title"] == "Example"
    assert obs["ax_tree_digest"] == ""
    assert obs["ax_fingerprint"] == _EMPTY_FINGERPRINT
    assert obs["last_action"] is None


_BUTTON_HTML = "<!DOCTYPE html><html><body><button>Click</button></body></html>"
_BUTTON_DATA_URL = f"data:text/html;base64,{base64.b64encode(_BUTTON_HTML.encode()).decode()}"


def test_cdp_session_reused_across_n_observations(playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(_BUTTON_DATA_URL)
        with unittest.mock.patch.object(
            browser._page.context,
            "new_cdp_session",
            wraps=browser._page.context.new_cdp_session,
        ) as spy:
            observations = [build_observation(browser, None) for _ in range(10)]

    assert spy.call_count == 1
    assert all(obs["ax_tree_digest"] != "" for obs in observations)


def test_new_page_invalidates_cached_session(playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(_BUTTON_DATA_URL)
        with unittest.mock.patch.object(
            browser._context,
            "new_cdp_session",
            wraps=browser._context.new_cdp_session,
        ) as spy:
            build_observation(browser, None)
            old_page = browser._page

            first_session = browser._cdp_sessions[id(old_page)]
            first_session.detach = unittest.mock.Mock(wraps=first_session.detach)

            browser._page = browser._context.new_page()
            new_page = browser._page
            browser._page.goto(_BUTTON_DATA_URL)
            build_observation(browser, None)

            assert first_session.detach.call_count == 1
            assert len(browser._cdp_sessions) == 1
            assert id(new_page) in browser._cdp_sessions

            browser._page.close()
            browser._page = old_page

    assert spy.call_count == 2


def test_cdp_send_failure_evicts_cached_session():
    cdp = types.SimpleNamespace(
        send=unittest.mock.Mock(side_effect=RuntimeError("send boom")),
        detach=unittest.mock.Mock(),
    )

    fake_context = types.SimpleNamespace(
        new_cdp_session=unittest.mock.Mock(return_value=cdp),
    )
    fake_page = types.SimpleNamespace(
        url="http://example.com/",
        title=lambda: "Example",
        context=fake_context,
    )
    fake_browser = types.SimpleNamespace(_page=fake_page, _cdp_sessions={})

    obs = build_observation(fake_browser, None)
    assert obs["ax_tree_digest"] == ""
    assert obs["ax_fingerprint"] == _EMPTY_FINGERPRINT

    assert cdp.detach.call_count == 1
    assert fake_browser._cdp_sessions == {}

    build_observation(fake_browser, None)
    assert fake_context.new_cdp_session.call_count == 2


def test_browser_exit_detaches_without_raising(playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(_BUTTON_DATA_URL)
        build_observation(browser, None)
        assert len(browser._cdp_sessions) == 1

    assert browser._cdp_sessions == {}
