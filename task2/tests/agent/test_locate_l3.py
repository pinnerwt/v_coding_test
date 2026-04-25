from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from agent.browser import Browser
from agent.llm import ChatResponse, LLMError, Usage
from agent.locate import (
    LocateResult,
    LocatorMiss,
    locate,
    locate_l3,
)


def _ok_chat_response(content: str) -> ChatResponse:
    return ChatResponse(
        content=content,
        tool_calls=[],
        finish_reason="stop",
        model="stub",
        usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        raw={},
    )


def _make_chat_stub(
    *, content: str | None = None, fail_if_called: bool = False
) -> Callable[..., ChatResponse]:
    calls: list[dict] = []

    def stub(messages, **kwargs):
        if fail_if_called:
            raise AssertionError("llm_chat was invoked but the test expected no call")
        calls.append({"messages": messages, "kwargs": kwargs})
        return _ok_chat_response(content if content is not None else "")

    stub.calls = calls  # type: ignore[attr-defined]
    return stub


def test_locate_l3_three_save_picks_middle(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content=json.dumps({"index": 1}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l3_three_save.html")
        result = locate_l3(b._page, role="button", name="Save", llm_chat=stub)
        assert isinstance(result, LocateResult)
        assert result.tier == "L3_rerank"
        assert result.confidence == 0.8
        assert result.role == "button"
        assert result.name == "Save"
        loc = b._page.locator(result.selector)
        assert loc.count() == 1
        section_label = loc.first.evaluate(
            "el => el.closest('section') && el.closest('section').getAttribute('aria-label')"
        )
        assert section_label == "Settings"
        assert result.ax_fingerprint


def test_locate_l3_single_candidate_skips_llm(fixture_server, playwright_chromium):
    stub = _make_chat_stub(fail_if_called=True)
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l1.html")
        result = locate_l3(b._page, role="button", name="Submit", llm_chat=stub)
        assert result.tier == "L3_rerank"
        assert result.confidence == 0.8
        assert stub.calls == []  # type: ignore[attr-defined]
        loc = b._page.locator(result.selector)
        assert loc.count() == 1


def test_locate_l3_zero_candidates_skips_llm(fixture_server, playwright_chromium):
    stub = _make_chat_stub(fail_if_called=True)
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l3_three_save.html")
        with pytest.raises(LocatorMiss) as ei:
            locate_l3(b._page, role="button", name="Refund", llm_chat=stub)
        assert ei.value.reason == "zero_matches"
        assert ei.value.match_count == 0
        assert stub.calls == []  # type: ignore[attr-defined]


def test_locate_l3_malformed_json_raises_ambiguous(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content="not even close to JSON")
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l3_three_save.html")
        with pytest.raises(LocatorMiss) as ei:
            locate_l3(b._page, role="button", name="Save", llm_chat=stub)
        assert ei.value.reason == "ambiguous"
        assert ei.value.match_count == 3


def test_locate_l3_index_out_of_range_raises_ambiguous(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content=json.dumps({"index": 99}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l3_three_save.html")
        with pytest.raises(LocatorMiss) as ei:
            locate_l3(b._page, role="button", name="Save", llm_chat=stub)
        assert ei.value.reason == "ambiguous"
        assert ei.value.match_count == 3


def test_locate_l3_index_negative_raises_ambiguous(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content=json.dumps({"index": -1}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l3_three_save.html")
        with pytest.raises(LocatorMiss) as ei:
            locate_l3(b._page, role="button", name="Save", llm_chat=stub)
        assert ei.value.reason == "ambiguous"
        assert ei.value.match_count == 3


def test_locate_l3_missing_index_field_raises_ambiguous(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content=json.dumps({"selected": 0}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l3_three_save.html")
        with pytest.raises(LocatorMiss) as ei:
            locate_l3(b._page, role="button", name="Save", llm_chat=stub)
        assert ei.value.reason == "ambiguous"
        assert ei.value.match_count == 3


def test_locate_l3_non_integer_index_raises_ambiguous(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content=json.dumps({"index": "1"}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l3_three_save.html")
        with pytest.raises(LocatorMiss) as ei:
            locate_l3(b._page, role="button", name="Save", llm_chat=stub)
        assert ei.value.reason == "ambiguous"
        assert ei.value.match_count == 3


def test_locate_l3_selector_round_trips(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content=json.dumps({"index": 2}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l3_three_save.html")
        result = locate_l3(b._page, role="button", name="Save", llm_chat=stub)
        loc = b._page.locator(result.selector)
        assert loc.count() == 1
        text = (loc.first.text_content() or "").strip()
        assert text == "Save"
        section_label = loc.first.evaluate(
            "el => el.closest('section') && el.closest('section').getAttribute('aria-label')"
        )
        assert section_label == "Documents"


def test_locate_l3_fingerprint_stable_across_dom_changes(fixture_server, playwright_chromium):
    # First page: Settings is the second section (index 1).
    stub_a = _make_chat_stub(content=json.dumps({"index": 1}))
    # Alt page: Settings is the first section (index 0) — different DOM order, same heading.
    stub_b = _make_chat_stub(content=json.dumps({"index": 0}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l3_three_save.html")
        a = locate_l3(b._page, role="button", name="Save", llm_chat=stub_a)
        b.goto(f"{fixture_server}/locate_l3_three_save_alt.html")
        c = locate_l3(b._page, role="button", name="Save", llm_chat=stub_b)
    assert a.ax_fingerprint == c.ax_fingerprint


def test_locate_l3_prompt_contains_intent_and_candidates(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content=json.dumps({"index": 0}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l3_three_save.html")
        locate_l3(b._page, role="button", name="Save", llm_chat=stub)

    assert len(stub.calls) == 1  # type: ignore[attr-defined]
    messages = stub.calls[0]["messages"]  # type: ignore[attr-defined]
    blob = "\n".join(
        msg.get("content", "") for msg in messages if isinstance(msg.get("content"), str)
    )
    assert "Save" in blob
    assert "button" in blob
    for heading in ("Profile", "Settings", "Documents"):
        assert heading in blob


def test_locate_l3_llm_error_raises_ambiguous(fixture_server, playwright_chromium):
    def raising_stub(messages, **kwargs):
        raise LLMError("transport blew up", kind="transport")

    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l3_three_save.html")
        with pytest.raises(LocatorMiss) as ei:
            locate_l3(b._page, role="button", name="Save", llm_chat=raising_stub)
        assert ei.value.reason == "ambiguous"
        assert ei.value.match_count == 3


def test_locate_orchestrator_cascades_l1_ambiguous_to_l3(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content=json.dumps({"index": 0}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l3_three_save.html")
        result = locate(b._page, "Save button", llm_chat=stub)
        assert result.tier == "L3_rerank"
        assert result.role == "button"
        assert result.name == "Save"


def test_locate_orchestrator_surfaces_l3_ambiguous(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content="not JSON at all")
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l3_three_save.html")
        with pytest.raises(LocatorMiss) as ei:
            locate(b._page, "Save button", llm_chat=stub)
        assert ei.value.reason == "ambiguous"
        assert ei.value.match_count == 3
