from __future__ import annotations

import json

from agent.browser import Browser
from agent.llm import ChatResponse, ToolCall, Usage
from agent.loop import loop
from agent.trace import SupervisorEvent

_DUMMY_USAGE = Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2)

_PLAN_STUB = '{"steps": ["complete the task"], "expected_end_state": "task complete"}'


def _tool_call(name: str, args: dict, call_id: str = "tc-1") -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=json.dumps(args))


def _response_with_tool_call(tc: ToolCall) -> ChatResponse:
    return ChatResponse(
        content=None,
        tool_calls=[tc],
        finish_reason="tool_calls",
        model="fake",
        usage=_DUMMY_USAGE,
        raw={},
    )


def _plan_stub_response() -> ChatResponse:
    return ChatResponse(
        content=_PLAN_STUB,
        tool_calls=[],
        finish_reason="stop",
        model="fake",
        usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        raw={},
        usd=0.0,
    )


class _FakeLLMClient:
    def __init__(self, responses: list[ChatResponse]):
        self._responses = list(responses)
        self._index = 0

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        if tools is None:
            return _plan_stub_response()
        if self._index < len(self._responses):
            resp = self._responses[self._index]
            self._index += 1
            return resp
        return ChatResponse(
            content="I am thinking…",
            tool_calls=[],
            finish_reason="stop",
            model="fake",
            usage=_DUMMY_USAGE,
            raw={},
        )


def test_supervisor_event_premature_fail_literal():
    event = SupervisorEvent(
        run_id="r",
        seq=1,
        ts="",
        step_id=None,
        trigger_event_seq=0,
        classified_as="premature_fail",
        policy="halt",
        attempt=1,
    )
    assert event.classified_as == "premature_fail"


def test_loop_fail_step1_no_prior_action_is_rejected(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"

    events: list = []
    responses = [
        _response_with_tool_call(_tool_call("fail", {"reason": "nothing here"}, call_id="tc-f")),
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"ok": True},
                    "evidence": {"url": fixture_url, "text_snippet": "Hello"},
                },
                call_id="tc-done",
            )
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        result = loop("task", browser, fake_llm, events=events, max_steps=10)

    assert result.status != "failed"
    premature_events = [
        e for e in events if isinstance(e, SupervisorEvent) and e.classified_as == "premature_fail"
    ]
    assert len(premature_events) >= 1


def test_loop_fail_step2_after_read_is_honored(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"

    events: list = []
    responses = [
        _response_with_tool_call(_tool_call("read", {}, call_id="tc-read")),
        _response_with_tool_call(
            _tool_call("fail", {"reason": "could not find result"}, call_id="tc-f")
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        result = loop("task", browser, fake_llm, events=events, max_steps=10)

    assert result.status == "failed"
    premature_events = [
        e for e in events if isinstance(e, SupervisorEvent) and e.classified_as == "premature_fail"
    ]
    assert len(premature_events) == 0


def test_loop_fail_irrecoverable_keyword_honored_on_step1(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"

    events: list = []
    responses = [
        _response_with_tool_call(
            _tool_call("fail", {"reason": "login wall detected"}, call_id="tc-f")
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        result = loop("task", browser, fake_llm, events=events, max_steps=10)

    assert result.status == "failed"
    premature_events = [
        e for e in events if isinstance(e, SupervisorEvent) and e.classified_as == "premature_fail"
    ]
    assert len(premature_events) == 0


def test_loop_fail_step1_after_successful_click_is_honored(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"

    events: list = []
    responses = [
        _response_with_tool_call(
            _tool_call("click", {"intent": "Hello, loop heading"}, call_id="tc-click")
        ),
        _response_with_tool_call(_tool_call("fail", {"reason": "submit failed"}, call_id="tc-f")),
    ]
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        result = loop("task", browser, fake_llm, events=events, max_steps=10)

    assert result.status == "failed"
    premature_events = [
        e for e in events if isinstance(e, SupervisorEvent) and e.classified_as == "premature_fail"
    ]
    assert len(premature_events) == 0
