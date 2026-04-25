from __future__ import annotations

import dataclasses
import json

import pytest

from agent.llm import ChatResponse, ToolCall, Usage
from agent.loop import RunResult, loop

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DUMMY_USAGE = Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2)


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


def _response_no_tool_call() -> ChatResponse:
    return ChatResponse(
        content="I am thinking…",
        tool_calls=[],
        finish_reason="stop",
        model="fake",
        usage=_DUMMY_USAGE,
        raw={},
    )


class _FakeLLMClient:
    """Returns pre-canned ChatResponse objects in sequence."""

    def __init__(self, responses: list[ChatResponse]):
        self._responses = list(responses)
        self._index = 0

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        if self._index < len(self._responses):
            resp = self._responses[self._index]
            self._index += 1
            return resp
        # If all responses exhausted, return a no-op text response to exercise
        # the timeout path without raising.
        return _response_no_tool_call()


# ---------------------------------------------------------------------------
# RunResult tests
# ---------------------------------------------------------------------------


def test_run_result_is_frozen():
    result = RunResult(
        status="succeeded",
        result={"x": 1},
        evidence={"url": "http://a", "text_snippet": "a"},
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.status = "failed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Acceptance test: 2-step happy path
# ---------------------------------------------------------------------------


def test_loop_happy_path(fixture_server, playwright_chromium):
    from agent.browser import Browser

    fixture_url = f"{fixture_server}/loop_happy_path.html"

    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"heading": "Hello, loop"},
                    "evidence": {
                        "url": fixture_url,
                        "text_snippet": "Hello, loop",
                    },
                },
                call_id="tc-2",
            )
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("read the heading", browser, fake_llm)

    assert result.status == "succeeded"
    assert result.result == {"heading": "Hello, loop"}
    assert result.evidence is not None
    assert result.evidence["url"]
    assert result.evidence["text_snippet"]


# ---------------------------------------------------------------------------
# Timeout path
# ---------------------------------------------------------------------------


def test_loop_timeout(fixture_server, playwright_chromium):
    from agent.browser import Browser

    fixture_url = f"{fixture_server}/loop_happy_path.html"

    # The fake LLM always returns a no-op text response (no done/fail).
    fake_llm = _FakeLLMClient([])  # exhausted immediately → falls back to text responses

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        result = loop("task", browser, fake_llm, max_steps=2)

    assert result.status == "timeout"


# ---------------------------------------------------------------------------
# Fail path
# ---------------------------------------------------------------------------


def test_loop_fail(fixture_server, playwright_chromium):
    from agent.browser import Browser

    fixture_url = f"{fixture_server}/loop_happy_path.html"

    responses = [
        _response_with_tool_call(_tool_call("fail", {"reason": "blocked"}, call_id="tc-f")),
    ]
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        result = loop("task", browser, fake_llm)

    assert result.status == "failed"
    assert result.result is None


# ---------------------------------------------------------------------------
# Read tool dispatch — without intent (full body text)
# ---------------------------------------------------------------------------


def test_loop_read_no_intent(fixture_server, playwright_chromium):
    """Scenario: LLM calls read without intent — returns body text and loop continues."""
    from agent.browser import Browser

    fixture_url = f"{fixture_server}/loop_happy_path.html"

    # Step 1: goto, Step 2: read (no intent), Step 3: done
    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
        _response_with_tool_call(_tool_call("read", {}, call_id="tc-2")),
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"heading": "Hello, loop"},
                    "evidence": {
                        "url": fixture_url,
                        "text_snippet": "Hello, loop",
                    },
                },
                call_id="tc-3",
            )
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("read the heading", browser, fake_llm)

    assert result.status == "succeeded"
    assert result.result == {"heading": "Hello, loop"}


# ---------------------------------------------------------------------------
# Read tool dispatch — with intent (locate-based element read)
# ---------------------------------------------------------------------------


def test_loop_read_with_intent(fixture_server, playwright_chromium):
    """Scenario: LLM calls read with intent — uses locate to find element and returns text."""
    from agent.browser import Browser

    fixture_url = f"{fixture_server}/loop_happy_path.html"

    # Step 1: goto, Step 2: read with intent targeting the h1, Step 3: done
    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
        _response_with_tool_call(
            _tool_call("read", {"intent": "Hello, loop heading"}, call_id="tc-2")
        ),
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"heading": "Hello, loop"},
                    "evidence": {
                        "url": fixture_url,
                        "text_snippet": "Hello, loop",
                    },
                },
                call_id="tc-3",
            )
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("read the heading", browser, fake_llm)

    assert result.status == "succeeded"
    assert result.result == {"heading": "Hello, loop"}
