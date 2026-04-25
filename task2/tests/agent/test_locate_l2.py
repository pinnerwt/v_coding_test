from __future__ import annotations

import pytest

from agent.browser import Browser
from agent.locate import (
    LocateResult,
    LocatorMiss,
    locate,
    locate_l2,
)


def test_locate_l2_placeholder_unique(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l2_placeholder.html")
        result = locate_l2(b._page, role="textbox", name="Email address")
        assert isinstance(result, LocateResult)
        assert result.tier == "L2_dom"
        assert result.role == "textbox"
        assert result.name == "Email address"
        assert result.confidence == 0.7
        assert result.ax_fingerprint
        loc = b._page.locator(result.selector)
        assert loc.count() == 1
        tag = loc.first.evaluate("el => el.tagName")
        assert tag == "INPUT"
        placeholder = loc.first.evaluate("el => el.getAttribute('placeholder')")
        assert placeholder == "Email address"


def test_locate_l2_nonsemantic_clickable_unique(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l2_nonsemantic.html")
        result = locate_l2(b._page, role="button", name="Submit")
        assert result.tier == "L2_dom"
        assert result.role == "button"
        assert result.name == "Submit"
        loc = b._page.locator(result.selector)
        assert loc.count() == 1
        tag = loc.first.evaluate("el => el.tagName")
        assert tag == "DIV"
        cls = loc.first.evaluate("el => el.getAttribute('class')")
        assert cls == "btn"


def test_locate_l2_ambiguous(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l2_ambiguous.html")
        with pytest.raises(LocatorMiss) as excinfo:
            locate_l2(b._page, role="button", name="Save")
        assert excinfo.value.reason == "ambiguous"
        assert excinfo.value.match_count == 2


def test_locate_l2_zero_matches(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l2_placeholder.html")
        with pytest.raises(LocatorMiss) as excinfo:
            locate_l2(b._page, role="button", name="Refund")
        assert excinfo.value.reason == "zero_matches"
        assert excinfo.value.match_count == 0


def test_locate_l2_unsupported_role_short_circuits(
    fixture_server, playwright_chromium, monkeypatch
):
    import agent.locate as locate_module

    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l2_placeholder.html")

        original_locator = b._page.locator
        original_get_by_placeholder = b._page.get_by_placeholder
        original_get_by_role = b._page.get_by_role
        calls: list[str] = []

        def spy_locator(*args, **kwargs):
            calls.append("locator")
            return original_locator(*args, **kwargs)

        def spy_placeholder(*args, **kwargs):
            calls.append("get_by_placeholder")
            return original_get_by_placeholder(*args, **kwargs)

        def spy_role(*args, **kwargs):
            calls.append("get_by_role")
            return original_get_by_role(*args, **kwargs)

        monkeypatch.setattr(b._page, "locator", spy_locator)
        monkeypatch.setattr(b._page, "get_by_placeholder", spy_placeholder)
        monkeypatch.setattr(b._page, "get_by_role", spy_role)

        with pytest.raises(LocatorMiss) as excinfo:
            locate_module.locate_l2(b._page, role="heading", name="Welcome")
        assert excinfo.value.reason == "zero_matches"
        assert excinfo.value.match_count == 0
        assert calls == []


def test_locate_l2_empty_name_short_circuits(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l2_nonsemantic.html")
        with pytest.raises(LocatorMiss) as excinfo:
            locate_l2(b._page, role="button", name=None)
        assert excinfo.value.reason == "zero_matches"
        assert excinfo.value.match_count == 0


def test_locate_orchestrator_cascades_l1_zero_to_l2(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l2_nonsemantic.html")
        result = locate(b._page, "Submit button")
        assert result.tier == "L2_dom"
        assert result.role == "button"
        assert result.name == "Submit"


def test_locate_orchestrator_l1_ambiguous_now_cascades_to_l3(fixture_server, playwright_chromium):
    # Ticket #5 changes the cascade: L1 ambiguous now goes to L3, not propagation.
    # We mock the LLM to confirm L3 is reached; the L3 test module covers the
    # fingerprint/selector contract end-to-end.
    import json

    from agent.llm import ChatResponse, Usage

    def stub(messages, **kwargs):
        return ChatResponse(
            content=json.dumps({"index": 0}),
            tool_calls=[],
            finish_reason="stop",
            model="stub",
            usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
            raw={},
        )

    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l1.html")
        result = locate(b._page, "Save button", llm_chat=stub)
        assert result.tier == "L3_rerank"
        assert result.role == "button"
        assert result.name == "Save"


def test_locate_orchestrator_surfaces_l2_zero_match(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l2_placeholder.html")
        with pytest.raises(LocatorMiss) as excinfo:
            locate(b._page, "Refund button")
        assert excinfo.value.reason == "zero_matches"


def test_locate_l2_text_contains_selector_round_trips(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l2_substring.html")
        result = locate_l2(b._page, role="button", name="Save")
        loc = b._page.locator(result.selector)
        assert loc.count() == 1
        text = (loc.first.text_content() or "").strip()
        assert text == "Save changes"


def test_l2_fingerprint_independent_of_dom_path(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l2_nonsemantic.html")
        a = locate_l2(b._page, role="button", name="Submit")
        b.goto(f"{fixture_server}/locate_l2_nonsemantic_alt.html")
        c = locate_l2(b._page, role="button", name="Submit")
    assert a.ax_fingerprint == c.ax_fingerprint
