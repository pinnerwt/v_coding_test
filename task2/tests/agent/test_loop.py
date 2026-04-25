from __future__ import annotations

import dataclasses
import json

import pytest

from agent.browser import Browser
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


# ---------------------------------------------------------------------------
# Reliability: malformed tool arguments must not crash the loop.
# ---------------------------------------------------------------------------


def test_loop_handles_malformed_tool_arguments(fixture_server, playwright_chromium):
    """A model that emits non-JSON tool-call arguments must not crash the run.

    The loop must feed an error back to the model (as a tool-result message)
    and continue, so a single bad payload does not bypass max_steps and the
    RunResult contract.
    """
    fixture_url = f"{fixture_server}/loop_happy_path.html"

    bad_call = ToolCall(id="tc-bad", name="goto", arguments="{not valid json")
    good_done = _tool_call(
        "done",
        {
            "result": {"heading": "Hello, loop"},
            "evidence": {"url": fixture_url, "text_snippet": "Hello, loop"},
        },
        call_id="tc-done",
    )
    fake_llm = _FakeLLMClient(
        [_response_with_tool_call(bad_call), _response_with_tool_call(good_done)]
    )

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        result = loop("task", browser, fake_llm, max_steps=3)

    assert result.status == "succeeded"


# ---------------------------------------------------------------------------
# Reliability: unknown tool names must not crash the loop.
# ---------------------------------------------------------------------------


def test_loop_handles_unknown_tool_name(fixture_server, playwright_chromium):
    """A model that emits a hallucinated tool name must not crash the run.

    The loop must feed an error back as a tool-result message and continue.
    """
    fixture_url = f"{fixture_server}/loop_happy_path.html"

    unknown = _tool_call("frobnicate", {"x": 1}, call_id="tc-unk")
    good_done = _tool_call(
        "done",
        {
            "result": {"heading": "Hello, loop"},
            "evidence": {"url": fixture_url, "text_snippet": "Hello, loop"},
        },
        call_id="tc-done",
    )
    fake_llm = _FakeLLMClient(
        [_response_with_tool_call(unknown), _response_with_tool_call(good_done)]
    )

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        result = loop("task", browser, fake_llm, max_steps=3)

    assert result.status == "succeeded"


# ---------------------------------------------------------------------------
# Reliability: non-dict tool arguments must not crash the loop.
# ---------------------------------------------------------------------------


def test_loop_handles_non_dict_arguments(fixture_server, playwright_chromium):
    """Valid JSON that decodes to a non-dict (e.g. list) must not crash the run."""
    fixture_url = f"{fixture_server}/loop_happy_path.html"

    bad = ToolCall(id="tc-list", name="goto", arguments="[]")
    good_done = _tool_call(
        "done",
        {
            "result": {"heading": "Hello, loop"},
            "evidence": {"url": fixture_url, "text_snippet": "Hello, loop"},
        },
        call_id="tc-done",
    )
    fake_llm = _FakeLLMClient([_response_with_tool_call(bad), _response_with_tool_call(good_done)])

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        result = loop("task", browser, fake_llm, max_steps=3)

    assert result.status == "succeeded"


# ---------------------------------------------------------------------------
# Reliability: missing required tool args must not crash the loop.
# ---------------------------------------------------------------------------


def test_loop_handles_goto_missing_url(fixture_server, playwright_chromium):
    """A goto call with no 'url' key must not raise KeyError; loop continues."""
    fixture_url = f"{fixture_server}/loop_happy_path.html"

    bad = _tool_call("goto", {}, call_id="tc-empty")
    good_done = _tool_call(
        "done",
        {
            "result": {"heading": "Hello, loop"},
            "evidence": {"url": fixture_url, "text_snippet": "Hello, loop"},
        },
        call_id="tc-done",
    )
    fake_llm = _FakeLLMClient([_response_with_tool_call(bad), _response_with_tool_call(good_done)])

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        result = loop("task", browser, fake_llm, max_steps=3)

    assert result.status == "succeeded"


# ---------------------------------------------------------------------------
# Self-correction: L1 fails → supervisor escalates → L2 succeeds
# ---------------------------------------------------------------------------


def test_loop_self_correction(fixture_server, playwright_chromium):
    """Scenario: L1 misses (aria-label override) — supervisor escalates to L2 and run completes."""
    fixture_url = f"{fixture_server}/loop_self_correction.html"

    # Step 1: goto fixture, Step 2: read with intent, Step 3: done
    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
        _response_with_tool_call(_tool_call("read", {"intent": "Submit button"}, call_id="tc-2")),
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"clicked": True},
                    "evidence": {
                        "url": fixture_url,
                        "text_snippet": "Submit",
                    },
                },
                call_id="tc-3",
            )
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("click the Submit button", browser, fake_llm)

    assert result.status == "succeeded"


# ---------------------------------------------------------------------------
# Self-correction: L1 fails → L2 also fails → loop returns error string,
# continues, LLM still reaches done.
# ---------------------------------------------------------------------------


def test_loop_self_correction_l2_also_fails(fixture_server, playwright_chromium):
    """Scenario: L1 and L2 both miss — loop returns error string and LLM still reaches done."""
    fixture_url = f"{fixture_server}/index.html"

    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
        _response_with_tool_call(_tool_call("read", {"intent": "Submit button"}, call_id="tc-2")),
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"note": "error was fed back"},
                    "evidence": {
                        "url": fixture_url,
                        "text_snippet": "Hello",
                    },
                },
                call_id="tc-3",
            )
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("click the Submit button", browser, fake_llm)

    # Loop must not crash; the error string was fed back and the LLM called done.
    assert result.status == "succeeded"


# ---------------------------------------------------------------------------
# Self-correction: supervisor max_attempts exhausted — loop returns error
# string gracefully (does not crash or raise).
# ---------------------------------------------------------------------------


def test_loop_self_correction_supervisor_halt(fixture_server, playwright_chromium):
    """Scenario: supervisor max_attempts exhausted — loop returns error string gracefully."""
    fixture_url = f"{fixture_server}/index.html"

    # 4 read calls exhaust the default max_attempts=3 and trigger the halt branch.
    read_tc = [
        _response_with_tool_call(
            _tool_call("read", {"intent": "Submit button"}, call_id=f"tc-r{i}")
        )
        for i in range(1, 5)
    ]
    responses = (
        [_response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-0"))]
        + read_tc
        + [
            _response_with_tool_call(
                _tool_call(
                    "done",
                    {
                        "result": {"note": "supervisor halted"},
                        "evidence": {
                            "url": fixture_url,
                            "text_snippet": "Hello",
                        },
                    },
                    call_id="tc-done",
                )
            ),
        ]
    )
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("click the Submit button", browser, fake_llm, max_steps=10)

    assert result.status == "succeeded"
