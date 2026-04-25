from __future__ import annotations

import base64
import json
from collections.abc import Callable

import httpx
import pytest
import respx

from agent.browser import Browser
from agent.llm import ChatResponse, LLMError, Usage
from agent.locate import (
    IntentParseError,
    LocateResult,
    LocatorMiss,
    locate,
    locate_l1,
    locate_l2,
    locate_l3,
    locate_l4,
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


def _make_chat_stub_raising(exc: BaseException) -> Callable[..., ChatResponse]:
    def stub(messages, **kwargs):
        raise exc

    return stub


def _make_dispatch_stub(*, l3_content: str, l4_content: str) -> Callable[..., ChatResponse]:
    """Dispatch based on the user message shape: list content => L4, str content => L3."""
    calls: list[dict] = []

    def stub(messages, **kwargs):
        calls.append({"messages": messages, "kwargs": kwargs})
        user = messages[1]
        if isinstance(user.get("content"), list):
            return _ok_chat_response(l4_content)
        return _ok_chat_response(l3_content)

    stub.calls = calls  # type: ignore[attr-defined]
    return stub


def test_locate_l4_happy_path_clicks_target_center(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content=json.dumps({"bbox": [100, 200, 80, 40]}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l4_no_metadata.html")
        b._page.set_viewport_size({"width": 1280, "height": 800})
        result = locate_l4(b._page, role="button", name=None, intent="Submit button", llm_chat=stub)
        assert isinstance(result, LocateResult)
        assert result.tier == "L4_vision"
        assert result.confidence == 0.5
        assert result.coords == (140, 220)
        assert result.selector == ""
        assert result.ax_fingerprint
        b.click_at(*result.coords)
        click = b._page.evaluate("() => window.__l4_click")
        assert click == {"x": 140, "y": 220, "target": "target"}


def test_locate_l4_malformed_json_raises_vision_miss(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content="not even close to JSON")
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l4_no_metadata.html")
        with pytest.raises(LocatorMiss) as ei:
            locate_l4(b._page, role="button", name=None, intent="Submit button", llm_chat=stub)
        assert ei.value.reason == "vision_miss"
        assert ei.value.match_count == 0


def test_locate_l4_missing_bbox_field_raises_vision_miss(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content=json.dumps({"box": [10, 20, 30, 40]}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l4_no_metadata.html")
        with pytest.raises(LocatorMiss) as ei:
            locate_l4(b._page, role="button", name=None, intent="Submit button", llm_chat=stub)
        assert ei.value.reason == "vision_miss"


def test_locate_l4_wrong_arity_raises_vision_miss(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content=json.dumps({"bbox": [10, 20, 30]}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l4_no_metadata.html")
        with pytest.raises(LocatorMiss) as ei:
            locate_l4(b._page, role="button", name=None, intent="Submit button", llm_chat=stub)
        assert ei.value.reason == "vision_miss"


def test_locate_l4_zero_width_raises_vision_miss(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content=json.dumps({"bbox": [10, 20, 0, 40]}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l4_no_metadata.html")
        with pytest.raises(LocatorMiss) as ei:
            locate_l4(b._page, role="button", name=None, intent="Submit button", llm_chat=stub)
        assert ei.value.reason == "vision_miss"


def test_locate_l4_zero_height_raises_vision_miss(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content=json.dumps({"bbox": [10, 20, 30, 0]}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l4_no_metadata.html")
        with pytest.raises(LocatorMiss) as ei:
            locate_l4(b._page, role="button", name=None, intent="Submit button", llm_chat=stub)
        assert ei.value.reason == "vision_miss"


def test_locate_l4_negative_origin_raises_vision_miss(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content=json.dumps({"bbox": [-1, 20, 30, 40]}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l4_no_metadata.html")
        with pytest.raises(LocatorMiss) as ei:
            locate_l4(b._page, role="button", name=None, intent="Submit button", llm_chat=stub)
        assert ei.value.reason == "vision_miss"


def test_locate_l4_out_of_viewport_raises_vision_miss(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content=json.dumps({"bbox": [1200, 750, 200, 200]}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l4_no_metadata.html")
        b._page.set_viewport_size({"width": 1280, "height": 800})
        with pytest.raises(LocatorMiss) as ei:
            locate_l4(b._page, role="button", name=None, intent="Submit button", llm_chat=stub)
        assert ei.value.reason == "vision_miss"


def test_locate_l4_non_numeric_bbox_raises_vision_miss(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content=json.dumps({"bbox": ["10", 20, 30, 40]}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l4_no_metadata.html")
        with pytest.raises(LocatorMiss) as ei:
            locate_l4(b._page, role="button", name=None, intent="Submit button", llm_chat=stub)
        assert ei.value.reason == "vision_miss"


def test_locate_l4_nan_bbox_raises_vision_miss(fixture_server, playwright_chromium):
    # Python's json.loads accepts non-strict NaN; the parser must still reject it via math.isfinite.
    stub = _make_chat_stub(content='{"bbox": [NaN, 20, 30, 40]}')
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l4_no_metadata.html")
        with pytest.raises(LocatorMiss) as ei:
            locate_l4(b._page, role="button", name=None, intent="Submit button", llm_chat=stub)
        assert ei.value.reason == "vision_miss"


def test_locate_l4_float_bbox_is_rounded(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content=json.dumps({"bbox": [99.6, 200.4, 80.0, 40.0]}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l4_no_metadata.html")
        b._page.set_viewport_size({"width": 1280, "height": 800})
        result = locate_l4(b._page, role="button", name=None, intent="Submit button", llm_chat=stub)
        assert result.coords == (140, 220)


def test_locate_l4_llm_transport_error_raises_vision_miss(fixture_server, playwright_chromium):
    err = LLMError("transport boom", kind="transport")
    stub = _make_chat_stub_raising(err)
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l4_no_metadata.html")
        with pytest.raises(LocatorMiss) as ei:
            locate_l4(b._page, role="button", name=None, intent="Submit button", llm_chat=stub)
        assert ei.value.reason == "vision_miss"
        assert ei.value.match_count == 0
        assert ei.value.__cause__ is err


def test_locate_l4_prompt_shape_carries_image_data_url(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content=json.dumps({"bbox": [100, 200, 80, 40]}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l4_no_metadata.html")
        b._page.set_viewport_size({"width": 1280, "height": 800})
        locate_l4(b._page, role="button", name=None, intent="Submit button", llm_chat=stub)

    assert len(stub.calls) == 1  # type: ignore[attr-defined]
    messages = stub.calls[0]["messages"]  # type: ignore[attr-defined]
    assert len(messages) == 2

    system_msg = messages[0]
    assert system_msg["role"] == "system"
    assert "bbox" in system_msg["content"]

    user_msg = messages[1]
    assert user_msg["role"] == "user"
    assert isinstance(user_msg["content"], list)
    text_parts = [c for c in user_msg["content"] if c.get("type") == "text"]
    image_parts = [c for c in user_msg["content"] if c.get("type") == "image_url"]
    assert len(text_parts) == 1
    assert "Submit button" in text_parts[0]["text"]
    assert len(image_parts) == 1
    url = image_parts[0]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    decoded = base64.b64decode(url.split(",", 1)[1])
    assert decoded.startswith(b"\x89PNG\r\n\x1a\n")


def test_locate_l4_viewport_size_none_raises_vision_miss_without_calling_llm(
    fixture_server, playwright_chromium, monkeypatch
):
    stub = _make_chat_stub(fail_if_called=True)
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l4_no_metadata.html")
        monkeypatch.setattr(type(b._page), "viewport_size", property(lambda self: None))
        with pytest.raises(LocatorMiss) as ei:
            locate_l4(b._page, role="button", name=None, intent="Submit button", llm_chat=stub)
        assert ei.value.reason == "vision_miss"
    assert stub.calls == []  # type: ignore[attr-defined]


def test_locate_l4_fingerprint_stable_for_same_intent_and_center(
    fixture_server, playwright_chromium
):
    stub_a = _make_chat_stub(content=json.dumps({"bbox": [100, 200, 80, 40]}))
    stub_b = _make_chat_stub(content=json.dumps({"bbox": [100, 200, 80, 40]}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l4_no_metadata.html")
        b._page.set_viewport_size({"width": 1280, "height": 800})
        a = locate_l4(b._page, role="button", name=None, intent="Submit button", llm_chat=stub_a)
        c = locate_l4(b._page, role="button", name=None, intent="Submit button", llm_chat=stub_b)
    assert a.ax_fingerprint == c.ax_fingerprint


def test_locate_l4_fingerprint_changes_with_center(fixture_server, playwright_chromium):
    stub_a = _make_chat_stub(content=json.dumps({"bbox": [100, 200, 80, 40]}))
    stub_b = _make_chat_stub(content=json.dumps({"bbox": [300, 400, 60, 20]}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l4_no_metadata.html")
        b._page.set_viewport_size({"width": 1280, "height": 800})
        a = locate_l4(b._page, role="button", name=None, intent="Submit button", llm_chat=stub_a)
        c = locate_l4(b._page, role="button", name=None, intent="Submit button", llm_chat=stub_b)
    assert a.ax_fingerprint != c.ax_fingerprint


def test_locate_orchestrator_cascades_l1_zero_l2_miss_to_l4(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content=json.dumps({"bbox": [100, 200, 80, 40]}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l4_no_metadata.html")
        b._page.set_viewport_size({"width": 1280, "height": 800})
        result = locate(b._page, "Submit button", llm_chat=stub)
        assert result.tier == "L4_vision"
        assert result.coords == (140, 220)


def test_locate_orchestrator_cascades_l1_ambiguous_l3_malformed_to_l4(
    fixture_server, playwright_chromium
):
    stub = _make_dispatch_stub(
        l3_content="not JSON at all",
        l4_content=json.dumps({"bbox": [10, 20, 30, 40]}),
    )
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l3_three_save.html")
        b._page.set_viewport_size({"width": 1280, "height": 800})
        result = locate(b._page, "Save button", llm_chat=stub)
        assert result.tier == "L4_vision"


def test_locate_orchestrator_l1_success_does_not_invoke_llm(fixture_server, playwright_chromium):
    stub = _make_chat_stub(fail_if_called=True)
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l1.html")
        result = locate(b._page, "Submit button", llm_chat=stub)
        assert result.tier == "L1_ax"
    assert stub.calls == []  # type: ignore[attr-defined]


def test_locate_orchestrator_intent_parse_error_does_not_invoke_llm(
    fixture_server, playwright_chromium
):
    stub = _make_chat_stub(fail_if_called=True)
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l1.html")
        with pytest.raises(IntentParseError):
            locate(b._page, "do the thing", llm_chat=stub)
    assert stub.calls == []  # type: ignore[attr-defined]


def test_locate_orchestrator_surfaces_vision_miss_when_all_tiers_fail(
    fixture_server, playwright_chromium
):
    stub = _make_chat_stub(content="not JSON at all")
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l4_no_metadata.html")
        with pytest.raises(LocatorMiss) as ei:
            locate(b._page, "Submit button", llm_chat=stub)
        assert ei.value.reason == "vision_miss"
        assert ei.value.match_count == 0


def test_l1_result_has_coords_none(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l1.html")
        result = locate_l1(b._page, role="button", name="Submit")
        assert result.coords is None


def test_l2_result_has_coords_none(fixture_server, playwright_chromium):
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l2_placeholder.html")
        result = locate_l2(b._page, role="textbox", name="Email address")
        assert result.coords is None


def test_l3_result_has_coords_none(fixture_server, playwright_chromium):
    stub = _make_chat_stub(content=json.dumps({"index": 1}))
    with Browser(playwright_browser=playwright_chromium) as b:
        b.goto(f"{fixture_server}/locate_l3_three_save.html")
        result = locate_l3(b._page, role="button", name="Save", llm_chat=stub)
        assert result.coords is None


@respx.mock
def test_locate_l4_default_chat_honors_llm_base_url(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "http://vision.example.test")
    monkeypatch.setenv("LLM_MODEL", "stub-vision")
    route = respx.post("http://vision.example.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "x",
                "object": "chat.completion",
                "model": "stub-vision",
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": json.dumps({"bbox": [10, 20, 30, 40]}),
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            },
        )
    )

    class _StubPage:
        @property
        def viewport_size(self):
            return {"width": 1280, "height": 800}

        def screenshot(self, *, full_page=False, scale="device"):
            return base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgAAIAAAUAAeImBZsAAAAASUVORK5CYII="
            )

    locate_l4(_StubPage(), role="button", name=None, intent="Submit button")

    assert route.called
    assert route.calls.last.request.url == "http://vision.example.test/v1/chat/completions"


def test_locate_l4_screenshots_in_css_pixel_scale():
    # Playwright's page.screenshot defaults to scale="device", but page.mouse.click
    # takes CSS pixels — on deviceScaleFactor != 1 contexts the bbox coords from a
    # device-scaled image would not line up with the click target. L4 must request
    # CSS-scale screenshots so the model's bbox coords are directly clickable.
    captured: dict = {}

    class _StubPage:
        @property
        def viewport_size(self):
            return {"width": 1280, "height": 800}

        def screenshot(self, *, full_page=False, scale="device"):
            captured["full_page"] = full_page
            captured["scale"] = scale
            return base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgAAIAAAUAAeImBZsAAAAASUVORK5CYII="
            )

    stub = _make_chat_stub(content=json.dumps({"bbox": [10, 20, 30, 40]}))
    locate_l4(_StubPage(), role="button", name=None, intent="Submit button", llm_chat=stub)
    assert captured["scale"] == "css"
    assert captured["full_page"] is False
