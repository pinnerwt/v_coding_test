from __future__ import annotations

import dataclasses
import json
from datetime import datetime
from unittest.mock import patch

import pytest

from agent.browser import Browser
from agent.llm import ChatResponse, ToolCall, Usage
from agent.loop import RunResult, _build_system_prompt, loop
from agent.trace import (
    ActEvent,
    LocateEvent,
    PlanEvent,
    Run,
    RunBudget,
    RunLLM,
    SupervisorEvent,
    TraceWriter,
)

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


_PLAN_STUB = '{"steps": ["complete the task"], "expected_end_state": "task complete"}'


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
    """Returns pre-canned ChatResponse objects in sequence.

    Planner calls (tools=None) are answered with a stub plan response so
    existing tests do not need to prepend a planner response to their lists.
    """

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


def test_loop_read_intent_locator_resolved_but_read_raises_does_not_crash(
    fixture_server, playwright_chromium
):
    """Regression: ElementNotFound from browser.read() after a successful locate must surface
    as an Error: tool result so the loop can continue, not propagate out of the run."""
    from agent.browser import ElementNotFound

    fixture_url = f"{fixture_server}/loop_happy_path.html"
    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
        _response_with_tool_call(
            _tool_call("read", {"intent": "Hello, loop heading"}, call_id="tc-2")
        ),
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"ok": False},
                    "evidence": {"url": fixture_url, "text_snippet": "n/a"},
                },
                call_id="tc-3",
            )
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)

        def _raises(_selector):
            raise ElementNotFound("element vanished after locate")

        browser.read = _raises
        result = loop("read the heading", browser, fake_llm)

    assert result.status in {"succeeded", "unverified"}
    assert result.steps == 3


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
    """Scenario: supervisor max_attempts exhausted — loop returns error string gracefully.

    A successful click before the reads keeps any_action_succeeded=True in the
    no-progress buffer long enough for 4 locator-miss steps to exhaust max_attempts=3
    and trigger the halt+replan path before no-progress fires.
    """
    fixture_url = f"{fixture_server}/loop_self_correction.html"

    # 4 read calls for a nonexistent element exhaust max_attempts=3 and trigger halt.
    # The preceding click(Submit) succeeds and prevents the no-progress buffer from
    # filling with all-False entries before the supervisor halt fires.
    read_tc = [
        _response_with_tool_call(
            _tool_call("read", {"intent": "NonExistent heading"}, call_id=f"tc-r{i}")
        )
        for i in range(1, 5)
    ]
    responses = (
        [_response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-0"))]
        + [
            _response_with_tool_call(
                _tool_call("click", {"intent": "action button"}, call_id="tc-click")
            )
        ]
        + read_tc
        + [
            _response_with_tool_call(
                _tool_call(
                    "done",
                    {
                        "result": {"note": "supervisor halted"},
                        "evidence": {
                            "url": fixture_url,
                            "text_snippet": "Self-correction",
                        },
                    },
                    call_id="tc-done",
                )
            ),
        ]
    )
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("click the Submit button", browser, fake_llm, max_steps=15)

    assert result.status == "succeeded"


# ---------------------------------------------------------------------------
# Evidence guard: done routes valid evidence to "succeeded", invalid to "unverified"
# ---------------------------------------------------------------------------


def _run_done(
    done_args_factory,
    fixture_server,
    playwright_chromium,
) -> RunResult:
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
        _response_with_tool_call(
            _tool_call("done", done_args_factory(fixture_url), call_id="tc-2")
        ),
    ]
    fake_llm = _FakeLLMClient(responses)
    with Browser(playwright_browser=playwright_chromium) as browser:
        return loop("read the heading", browser, fake_llm)


@pytest.mark.parametrize(
    ("done_args_factory", "expected_reason_substr"),
    [
        # missing 'evidence' key entirely
        (lambda _url: {"result": {}}, None),
        # evidence={} → both fields missing
        (lambda _url: {"result": {}, "evidence": {}}, None),
        # only text_snippet present → url reason
        (lambda _url: {"result": {}, "evidence": {"text_snippet": "Hello, loop"}}, "url"),
        # only url present → text_snippet reason
        (lambda url: {"result": {}, "evidence": {"url": url}}, "text_snippet"),
    ],
    ids=["no_evidence_key", "empty_evidence", "missing_url", "missing_text_snippet"],
)
def test_loop_done_without_valid_evidence_is_unverified(
    fixture_server,
    playwright_chromium,
    done_args_factory,
    expected_reason_substr,
):
    result = _run_done(done_args_factory, fixture_server, playwright_chromium)

    assert result.status == "unverified"
    assert result.verifier is not None
    assert result.verifier["ok"] is False
    assert result.verifier["reasons"]
    if expected_reason_substr is not None:
        assert any(expected_reason_substr in r for r in result.verifier["reasons"])


def test_loop_done_with_valid_evidence(fixture_server, playwright_chromium):
    result = _run_done(
        lambda url: {
            "result": {"heading": "Hello, loop"},
            "evidence": {"url": url, "text_snippet": "Hello, loop"},
        },
        fixture_server,
        playwright_chromium,
    )

    assert result.status == "succeeded"
    assert result.verifier == {"ok": True, "reasons": []}


# ---------------------------------------------------------------------------
# Metrics: 2-step run accumulates tokens, usd, latency
# ---------------------------------------------------------------------------


def _usage(prompt: int, completion: int) -> Usage:
    return Usage(
        prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion
    )


def _resp_with_tool_and_usage(
    tc: ToolCall, prompt: int, completion: int, usd: float
) -> ChatResponse:
    return ChatResponse(
        content=None,
        tool_calls=[tc],
        finish_reason="tool_calls",
        model="fake",
        usage=_usage(prompt, completion),
        raw={},
        usd=usd,
    )


def test_loop_metrics_two_step_run(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"

    responses = [
        _resp_with_tool_and_usage(
            _tool_call("goto", {"url": fixture_url}, call_id="tc-1"),
            prompt=100,
            completion=10,
            usd=0.00022,
        ),
        _resp_with_tool_and_usage(
            _tool_call(
                "done",
                {
                    "result": {"heading": "Hello, loop"},
                    "evidence": {"url": fixture_url, "text_snippet": "Hello, loop"},
                },
                call_id="tc-2",
            ),
            prompt=150,
            completion=20,
            usd=0.00034,
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("read the heading", browser, fake_llm)

    assert result.steps == 2
    assert result.prompt_tokens == 250
    assert result.completion_tokens == 30
    assert abs(result.usd - 0.00056) < 1e-9
    assert result.latency_ms_total > 0
    assert len(result.latency_ms_per_step) == 2
    assert len(result.step_breakdown) == 2


def test_loop_metrics_timeout_path(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"

    fake_llm = _FakeLLMClient([])

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        result = loop("task", browser, fake_llm, max_steps=2)

    assert result.status == "timeout"
    assert result.steps == 2
    assert len(result.latency_ms_per_step) == 2


def test_loop_metrics_step_breakdown_keys(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"

    responses = [
        _resp_with_tool_and_usage(
            _tool_call("goto", {"url": fixture_url}, call_id="tc-1"),
            prompt=100,
            completion=10,
            usd=0.00022,
        ),
        _resp_with_tool_and_usage(
            _tool_call(
                "done",
                {
                    "result": {"heading": "Hello, loop"},
                    "evidence": {"url": fixture_url, "text_snippet": "Hello, loop"},
                },
                call_id="tc-2",
            ),
            prompt=150,
            completion=20,
            usd=0.00034,
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("read the heading", browser, fake_llm)

    bd = result.step_breakdown[0]
    for key in ("step", "latency_ms", "prompt_tokens", "completion_tokens", "usd", "tool_calls"):
        assert key in bd, f"step_breakdown missing key: {key}"
    assert bd["step"] == 1
    assert isinstance(bd["tool_calls"], list)


# ---------------------------------------------------------------------------
# AX-tree observation: loop integration (red until loop uses observe.py)
# ---------------------------------------------------------------------------


class _CapturingLLMClient:
    def __init__(self, responses: list[ChatResponse]):
        self._responses = list(responses)
        self._index = 0
        self.captured_messages: list[dict] | None = None

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        if tools is None:
            return _plan_stub_response()
        if self.captured_messages is None:
            self.captured_messages = list(messages)
        if self._index < len(self._responses):
            resp = self._responses[self._index]
            self._index += 1
            return resp
        return _response_no_tool_call()


def _done_response(fixture_url: str, call_id: str = "tc-done") -> ChatResponse:
    return _response_with_tool_call(
        _tool_call(
            "done",
            {
                "result": {"ok": True},
                "evidence": {"url": fixture_url, "text_snippet": "Hello, loop"},
            },
            call_id=call_id,
        )
    )


def _extract_obs_json(content: str) -> dict:
    prefix = "Current state: "
    idx = content.find(prefix)
    assert idx >= 0, f"Expected 'Current state: ' in content: {content!r}"
    return json.loads(content[idx + len(prefix) :])


def test_observation_contains_ax_tree_digest_key(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    capturing_llm = _CapturingLLMClient([_done_response(fixture_url)])

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        loop("task", browser, capturing_llm, max_steps=2)

    assert capturing_llm.captured_messages is not None
    obs_msg = capturing_llm.captured_messages[1]
    content = obs_msg["content"]
    assert "Current state: " in content
    obs_json = _extract_obs_json(content)
    assert "ax_tree_digest" in obs_json


def test_observation_does_not_contain_legacy_text_key(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    capturing_llm = _CapturingLLMClient([_done_response(fixture_url)])

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        loop("task", browser, capturing_llm, max_steps=2)

    assert capturing_llm.captured_messages is not None
    obs_msg = capturing_llm.captured_messages[1]
    obs_json = _extract_obs_json(obs_msg["content"])
    assert "text" not in obs_json


def test_first_step_last_action_null(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    capturing_llm = _CapturingLLMClient([_done_response(fixture_url)])

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        loop("task", browser, capturing_llm, max_steps=2)

    assert capturing_llm.captured_messages is not None
    obs_msg = capturing_llm.captured_messages[1]
    obs_json = _extract_obs_json(obs_msg["content"])
    assert obs_json["last_actions"] == []


class _TwoStepCapturingClient:
    def __init__(self, fixture_url: str):
        self._fixture_url = fixture_url
        self._index = 0
        self.all_captures: list[list[dict]] = []

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        if tools is None:
            return _plan_stub_response()
        self.all_captures.append(list(messages))
        self._index += 1
        if self._index == 1:
            return _response_with_tool_call(
                _tool_call("goto", {"url": self._fixture_url}, call_id="tc-goto")
            )
        return _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"ok": True},
                    "evidence": {
                        "url": self._fixture_url,
                        "text_snippet": "Hello, loop",
                    },
                },
                call_id="tc-done",
            )
        )


def test_second_step_last_action_populated(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    two_step_llm = _TwoStepCapturingClient(fixture_url)

    with Browser(playwright_browser=playwright_chromium) as browser:
        loop("task", browser, two_step_llm, max_steps=3)

    assert len(two_step_llm.all_captures) >= 2
    step2_messages = two_step_llm.all_captures[1]
    obs_msg = next(
        m
        for m in reversed(step2_messages)
        if m["role"] == "user" and "Current state:" in m.get("content", "")
    )
    obs_json = _extract_obs_json(obs_msg["content"])
    assert obs_json["last_actions"]
    assert obs_json["last_actions"][0]["tool"] == "goto"


# ---------------------------------------------------------------------------
# Plan / replan integration tests (tasks 1.7–1.10)
# ---------------------------------------------------------------------------


class _PlanCapturingLLM:
    """LLM that returns canned responses in sequence and records all chat calls."""

    def __init__(self, plan_json: str, decision_responses: list[ChatResponse]):
        self._plan_json = plan_json
        self._decisions = list(decision_responses)
        self._call_index = 0
        self.all_messages: list[list[dict]] = []

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        self.all_messages.append(list(messages))
        idx = self._call_index
        self._call_index += 1
        if idx == 0:
            return _fake_text_response(self._plan_json)
        decision_idx = idx - 1
        if decision_idx < len(self._decisions):
            return self._decisions[decision_idx]
        return _response_no_tool_call()


def _fake_text_response(content: str) -> ChatResponse:
    return ChatResponse(
        content=content,
        tool_calls=[],
        finish_reason="stop",
        model="fake",
        usage=_DUMMY_USAGE,
        raw={},
    )


def test_plan_event_emitted_before_first_decision_event(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    plan_json = '{"steps": ["goto page", "read result"], "expected_end_state": "done"}'
    decision_responses = [
        _response_with_tool_call(
            _tool_call(
                "done",
                {"result": {"ok": True}, "evidence": {"url": fixture_url, "text_snippet": "Hello"}},
                call_id="tc-done",
            )
        )
    ]
    llm = _PlanCapturingLLM(plan_json, decision_responses)
    events: list = []

    with Browser(playwright_browser=playwright_chromium) as browser:
        loop("task", browser, llm, events=events)

    kinds = [e.kind for e in events]
    assert "plan" in kinds
    assert "decision" in kinds
    plan_idx = next(i for i, e in enumerate(events) if e.kind == "plan")
    decision_idx = next(i for i, e in enumerate(events) if e.kind == "decision")
    assert plan_idx < decision_idx


def test_decision_prompt_contains_plan_progress_from_step1(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    plan_json = '{"steps": ["find result", "return it"], "expected_end_state": "done"}'
    decision_responses = [
        _response_with_tool_call(
            _tool_call(
                "done",
                {"result": {"ok": True}, "evidence": {"url": fixture_url, "text_snippet": "Hello"}},
                call_id="tc-done",
            )
        )
    ]
    llm = _PlanCapturingLLM(plan_json, decision_responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        loop("task", browser, llm)

    assert len(llm.all_messages) >= 2
    decision_call_messages = llm.all_messages[1]
    user_msg = next(m for m in reversed(decision_call_messages) if m["role"] == "user")
    content = user_msg["content"]
    assert "Plan progress:" in content
    assert "1. find result" in content
    assert "2. return it" in content


def test_plan_progress_block_in_step2_decision_prompt(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    plan_json = '{"steps": ["goto page", "read result"], "expected_end_state": "done"}'

    class _TwoStepPlanLLM:
        def __init__(self):
            self._call_index = 0
            self.all_messages: list[list[dict]] = []

        def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
            self.all_messages.append(list(messages))
            idx = self._call_index
            self._call_index += 1
            if idx == 0:
                return _fake_text_response(plan_json)
            if idx == 1:
                return _response_with_tool_call(
                    _tool_call("goto", {"url": fixture_url}, call_id="tc-goto")
                )
            return _response_with_tool_call(
                _tool_call(
                    "done",
                    {
                        "result": {"ok": True},
                        "evidence": {"url": fixture_url, "text_snippet": "Hello, loop"},
                    },
                    call_id="tc-done",
                )
            )

    llm = _TwoStepPlanLLM()
    with Browser(playwright_browser=playwright_chromium) as browser:
        loop("task", browser, llm)

    assert len(llm.all_messages) >= 3
    step2_messages = llm.all_messages[2]
    user_msg = next(m for m in reversed(step2_messages) if m["role"] == "user")
    content = user_msg["content"]
    assert "Plan progress:" in content
    assert "1. goto page" in content
    assert "2. read result" in content


_DEFAULT_HALT_PLAN_JSON = '{"steps": ["step 1", "step 2"], "expected_end_state": "done"}'
_DEFAULT_HALT_REPLAN_JSON = (
    '{"steps": ["alt step 1", "alt step 2"], "expected_end_state": "alt done"}'
)


class _HaltReplanLLM:
    def __init__(
        self,
        fixture_url: str,
        plan_json: str = _DEFAULT_HALT_PLAN_JSON,
        replan_json: str = _DEFAULT_HALT_REPLAN_JSON,
    ):
        self._fixture_url = fixture_url
        self._plan_json = plan_json
        self._replan_json = replan_json
        self._call_index = 0
        self._replan_sent = False
        self._done_after_replan = False

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        idx = self._call_index
        self._call_index += 1
        if idx == 0:
            return _fake_text_response(self._plan_json)
        if tools is None and not self._replan_sent:
            self._replan_sent = True
            return _fake_text_response(self._replan_json)
        if self._replan_sent and tools is not None and not self._done_after_replan:
            self._done_after_replan = True
            return _response_with_tool_call(
                _tool_call(
                    "done",
                    {
                        "result": {"ok": True},
                        "evidence": {"url": self._fixture_url, "text_snippet": "Hello"},
                    },
                    call_id="tc-done",
                )
            )
        return _response_with_tool_call(
            _tool_call("read", {"intent": "Submit button"}, call_id=f"tc-r{idx}")
        )


def test_supervisor_halt_triggers_replan_event(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/index.html"
    llm = _HaltReplanLLM(fixture_url)
    events: list = []

    with Browser(playwright_browser=playwright_chromium) as browser:
        loop("click the Submit button", browser, llm, max_steps=10, events=events)

    plan_events = [e for e in events if e.kind == "plan"]
    replan_events = [e for e in plan_events if e.reason == "replan"]
    assert len(replan_events) >= 1


def test_second_supervisor_halt_returns_failed(fixture_server, playwright_chromium):
    plan_json = '{"steps": ["step 1"], "expected_end_state": "done"}'
    replan_json = '{"steps": ["alt step"], "expected_end_state": "alt done"}'

    class _DoubleHaltLLM:
        def __init__(self):
            self._call_index = 0
            self._replan_done = False

        def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
            idx = self._call_index
            self._call_index += 1
            if idx == 0:
                return _fake_text_response(plan_json)
            if tools is None and not self._replan_done:
                self._replan_done = True
                return _fake_text_response(replan_json)
            return _response_with_tool_call(
                _tool_call("read", {"intent": "Submit button"}, call_id=f"tc-r{idx}")
            )

    llm = _DoubleHaltLLM()
    events: list = []

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("click the Submit button", browser, llm, max_steps=20, events=events)

    assert result.status == "failed"
    plan_events = [e for e in events if e.kind == "plan"]
    replan_events = [e for e in plan_events if e.reason == "replan"]
    assert len(replan_events) == 1


def test_planner_tokens_included_in_run_metrics(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"

    class _TokenTrackingLLM:
        def __init__(self):
            self._call_index = 0

        def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
            idx = self._call_index
            self._call_index += 1
            if idx == 0:
                return ChatResponse(
                    content='{"steps": ["go"], "expected_end_state": "done"}',
                    tool_calls=[],
                    finish_reason="stop",
                    model="fake",
                    usage=Usage(prompt_tokens=50, completion_tokens=10, total_tokens=60),
                    raw={},
                    usd=0.0001,
                )
            return _resp_with_tool_and_usage(
                _tool_call(
                    "done",
                    {
                        "result": {"ok": True},
                        "evidence": {"url": fixture_url, "text_snippet": "Hello, loop"},
                    },
                    call_id="tc-done",
                ),
                prompt=100,
                completion=20,
                usd=0.0002,
            )

    llm = _TokenTrackingLLM()
    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("task", browser, llm)

    assert result.prompt_tokens == 150
    assert result.completion_tokens == 30
    assert abs(result.usd - 0.0003) < 1e-9


def test_loop_does_not_terminally_fail_on_unrelated_error_after_replan(
    fixture_server, playwright_chromium
):
    fixture_url = f"{fixture_server}/index.html"
    plan_json = '{"steps": ["step 1"], "expected_end_state": "done"}'
    replan_json = '{"steps": ["alt step"], "expected_end_state": "alt done"}'

    class _HaltThenGotoEmptyThenDoneLLM:
        def __init__(self):
            self._state = "plan"

        def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
            if self._state == "plan":
                self._state = "read"
                return _fake_text_response(plan_json)

            if tools is None:
                self._state = "goto_empty"
                return _fake_text_response(replan_json)

            if self._state == "read":
                return _response_with_tool_call(
                    _tool_call("read", {"intent": "Submit button"}, call_id="tc-read")
                )
            if self._state == "goto_empty":
                self._state = "done"
                return _response_with_tool_call(
                    _tool_call("goto", {"url": ""}, call_id="tc-empty-goto")
                )
            return _response_with_tool_call(
                _tool_call(
                    "done",
                    {
                        "result": {"ok": True},
                        "evidence": {
                            "url": fixture_url,
                            "text_snippet": "Hello",
                        },
                    },
                    call_id="tc-done",
                )
            )

    llm = _HaltThenGotoEmptyThenDoneLLM()

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("click the Submit button", browser, llm, max_steps=20)

    assert result.status == "succeeded"
    assert result.steps >= 3


def test_replan_does_not_leave_orphan_tool_call_in_message_history(
    fixture_server, playwright_chromium
):
    """OpenAI-compatible servers reject with HTTP 400 on unmatched tool_call IDs."""
    fixture_url = f"{fixture_server}/index.html"
    plan_json = '{"steps": ["step 1"], "expected_end_state": "done"}'
    replan_json = '{"steps": ["alt step"], "expected_end_state": "alt done"}'

    class _HaltReplanCapturingLLM:
        def __init__(self):
            self._call_index = 0
            self._replan_done = False
            self.all_messages: list[list[dict]] = []

        def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
            self.all_messages.append(list(messages))
            idx = self._call_index
            self._call_index += 1
            if idx == 0:
                return _fake_text_response(plan_json)
            if tools is None and not self._replan_done:
                self._replan_done = True
                return _fake_text_response(replan_json)
            if self._replan_done and tools is not None:
                return _response_with_tool_call(
                    _tool_call(
                        "done",
                        {
                            "result": {"ok": True},
                            "evidence": {"url": fixture_url, "text_snippet": "Hello"},
                        },
                        call_id="tc-done",
                    )
                )
            return _response_with_tool_call(
                _tool_call("read", {"intent": "Submit button"}, call_id=f"tc-r{idx}")
            )

    def _assert_tool_calls_have_responses(messages: list[dict]) -> None:
        pending: list[str] = []
        for msg in messages:
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                pending.extend(tc["id"] for tc in msg["tool_calls"])
            elif msg.get("role") == "tool":
                tool_call_id = msg.get("tool_call_id")
                assert tool_call_id in pending, (
                    f"tool message for unknown tool_call_id={tool_call_id!r}"
                )
                pending.remove(tool_call_id)
            elif msg.get("role") in ("user", "system"):
                assert not pending, (
                    f"orphan tool_calls before {msg.get('role')!r} message: {pending}"
                )

    llm = _HaltReplanCapturingLLM()

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("click the Submit button", browser, llm, max_steps=20)

    assert result.status == "succeeded"

    post_replan_messages = llm.all_messages[-1]
    _assert_tool_calls_have_responses(post_replan_messages)


class _ScriptedFirstStepClient:
    def __init__(self, first_step_calls: list[ToolCall], done_evidence_url: str):
        self._first_step_calls = first_step_calls
        self._done_evidence_url = done_evidence_url
        self._call_index = 0
        self.all_captures: list[list[dict]] = []

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        if tools is None:
            return _plan_stub_response()
        self.all_captures.append(list(messages))
        self._call_index += 1
        if self._call_index == 1:
            return ChatResponse(
                content=None,
                tool_calls=self._first_step_calls,
                finish_reason="tool_calls",
                model="fake",
                usage=_DUMMY_USAGE,
                raw={},
            )
        return _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"ok": True},
                    "evidence": {"url": self._done_evidence_url, "text_snippet": "Hello, loop"},
                },
                call_id="tc-done",
            )
        )


def _step_observation(captures: list[list[dict]], step_index: int) -> dict:
    messages = captures[step_index]
    obs_msg = next(
        m
        for m in reversed(messages)
        if m["role"] == "user" and "Current state:" in m.get("content", "")
    )
    return _extract_obs_json(obs_msg["content"])


def test_multi_tool_last_actions_both_in_observation(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    llm = _ScriptedFirstStepClient(
        [
            _tool_call("goto", {"url": fixture_url}, call_id="tc-goto"),
            _tool_call("read", {}, call_id="tc-read"),
        ],
        fixture_url,
    )
    with Browser(playwright_browser=playwright_chromium) as browser:
        loop("task", browser, llm, max_steps=3)

    assert len(llm.all_captures) >= 2
    obs = _step_observation(llm.all_captures, 1)
    assert len(obs["last_actions"]) == 2
    assert obs["last_actions"][0]["tool"] == "goto"
    assert obs["last_actions"][1]["tool"] == "read"


def test_single_tool_last_actions_length_one(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    two_step_llm = _TwoStepCapturingClient(fixture_url)

    with Browser(playwright_browser=playwright_chromium) as browser:
        loop("task", browser, two_step_llm, max_steps=3)

    assert len(two_step_llm.all_captures) >= 2
    obs = _step_observation(two_step_llm.all_captures, 1)
    assert len(obs["last_actions"]) == 1


def test_observation_uses_last_actions_key_not_last_action(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    capturing_llm = _CapturingLLMClient([_done_response(fixture_url)])

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        loop("task", browser, capturing_llm, max_steps=2)

    assert capturing_llm.captured_messages is not None
    obs_msg = capturing_llm.captured_messages[1]
    obs_json = _extract_obs_json(obs_msg["content"])
    assert "last_actions" in obs_json
    assert "last_action" not in obs_json


def test_error_outcome_preserved_in_last_actions(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    llm = _ScriptedFirstStepClient(
        [
            _tool_call("goto", {"url": fixture_url}, call_id="tc-good"),
            _tool_call("goto", {"url": ""}, call_id="tc-bad"),
        ],
        fixture_url,
    )
    with Browser(playwright_browser=playwright_chromium) as browser:
        loop("task", browser, llm, max_steps=3)

    assert len(llm.all_captures) >= 2
    obs = _step_observation(llm.all_captures, 1)
    assert len(obs["last_actions"]) == 2
    assert obs["last_actions"][0]["outcome"] == "ok"
    assert obs["last_actions"][1]["outcome"] == "error"
    assert "error" in obs["last_actions"][1]


# TraceWriter integration: PlanEvent wiring tests


def _make_writer_with_run(run_id: str) -> TraceWriter:
    writer = TraceWriter(":memory:")
    run = Run(
        run_id=run_id,
        task="test task",
        expect_schema=None,
        budget=RunBudget(steps=20, usd=1.0, seconds=300),
        llm=RunLLM(base_url="http://localhost:8090", model="fake", temperature=0.0, seed=None),
        agent_version="0.0.0",
        started_at="2024-01-01T00:00:00+00:00",
        ended_at=None,
        status=None,
        final=None,
        totals=None,
    )
    writer.open_run(run)
    return writer


def _all_rows(writer: TraceWriter) -> list[dict]:
    rows = writer._conn.execute("SELECT payload FROM traces_events ORDER BY seq ASC").fetchall()
    return [json.loads(r[0]) for r in rows]


def _plan_rows(writer: TraceWriter) -> list[dict]:
    return [r for r in _all_rows(writer) if r.get("kind") == "plan"]


def test_loop_with_trace_writer_plan_event_has_real_run_id(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    run_id = "test-run-1"
    writer = _make_writer_with_run(run_id)
    fake_llm = _FakeLLMClient([_done_response(fixture_url)])

    with Browser(playwright_browser=playwright_chromium) as browser:
        loop("task", browser, fake_llm, trace_writer=writer, run_id=run_id)

    plan_rows = _plan_rows(writer)
    assert len(plan_rows) >= 1
    assert plan_rows[0]["run_id"] == run_id
    writer.close()


def test_loop_with_trace_writer_plan_event_has_nonzero_seq(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    run_id = "test-run-2"
    writer = _make_writer_with_run(run_id)
    fake_llm = _FakeLLMClient([_done_response(fixture_url)])

    with Browser(playwright_browser=playwright_chromium) as browser:
        loop("task", browser, fake_llm, trace_writer=writer, run_id=run_id)

    plan_rows = _plan_rows(writer)
    assert len(plan_rows) >= 1
    assert plan_rows[0]["seq"] >= 1
    writer.close()


def test_loop_with_trace_writer_plan_event_has_iso_ts(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    run_id = "test-run-3"
    writer = _make_writer_with_run(run_id)
    fake_llm = _FakeLLMClient([_done_response(fixture_url)])

    with Browser(playwright_browser=playwright_chromium) as browser:
        loop("task", browser, fake_llm, trace_writer=writer, run_id=run_id)

    plan_rows = _plan_rows(writer)
    assert len(plan_rows) >= 1
    ts = plan_rows[0]["ts"]
    assert ts
    datetime.fromisoformat(ts)
    writer.close()


def test_loop_with_trace_writer_plan_event_seq_strictly_increasing(
    fixture_server, playwright_chromium
):
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    run_id = "test-run-4"
    writer = _make_writer_with_run(run_id)
    fake_llm = _FakeLLMClient([_done_response(fixture_url)])

    with Browser(playwright_browser=playwright_chromium) as browser:
        loop("task", browser, fake_llm, trace_writer=writer, run_id=run_id)

    rows = _all_rows(writer)
    seqs = [r["seq"] for r in rows]
    assert seqs == sorted(set(seqs))

    plan_seqs = [r["seq"] for r in rows if r["kind"] == "plan"]
    assert plan_seqs
    assert min(plan_seqs) >= 1
    writer.close()


def test_loop_with_trace_writer_replan_seq_after_initial_seq(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/index.html"
    run_id = "test-run-5"
    writer = _make_writer_with_run(run_id)
    fake_llm = _HaltReplanLLM(fixture_url)

    with Browser(playwright_browser=playwright_chromium) as browser:
        loop(
            "click the Submit button",
            browser,
            fake_llm,
            max_steps=10,
            trace_writer=writer,
            run_id=run_id,
        )

    plan_rows = _plan_rows(writer)
    replan_rows = [r for r in plan_rows if r.get("reason") == "replan"]
    initial_rows = [r for r in plan_rows if r.get("reason") == "initial"]
    assert len(replan_rows) >= 1
    assert len(initial_rows) >= 1
    assert initial_rows[0]["seq"] < replan_rows[0]["seq"]
    writer.close()


def test_loop_with_trace_writer_no_double_emit(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    run_id = "test-run-6"
    writer = _make_writer_with_run(run_id)
    fake_llm = _FakeLLMClient([_done_response(fixture_url)])
    events: list = []

    with Browser(playwright_browser=playwright_chromium) as browser:
        loop("task", browser, fake_llm, trace_writer=writer, run_id=run_id, events=events)

    plan_objects_in_events = [e for e in events if isinstance(e, PlanEvent)]
    assert plan_objects_in_events == []
    plan_rows = _plan_rows(writer)
    assert len(plan_rows) >= 1
    writer.close()


def test_loop_with_trace_writer_without_run_id_raises(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    writer = _make_writer_with_run("test-run-no-runid")
    fake_llm = _FakeLLMClient([_done_response(fixture_url)])

    with Browser(playwright_browser=playwright_chromium) as browser:
        with pytest.raises(ValueError, match="run_id"):
            loop("task", browser, fake_llm, trace_writer=writer)
    writer.close()


def test_loop_module_does_not_require_playwright(monkeypatch):
    # agent.replay imports agent.loop and must stay playwright-free; mask
    # playwright in sys.modules and re-import to enforce that contract.
    import importlib
    import sys

    monkeypatch.setitem(sys.modules, "playwright", None)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", None)
    for key in list(sys.modules):
        if key.startswith("agent"):
            monkeypatch.delitem(sys.modules, key, raising=False)

    importlib.import_module("agent.loop")


def test_interleaved_emitters_no_seq_error(fixture_server, playwright_chromium):
    """loop() emits PlanEvent at seq=1; caller then appends ObservationEvent at
    next_seq(); both rows persist with strictly-increasing seq and no SeqError."""
    from agent.trace import ObservationEvent

    fixture_url = f"{fixture_server}/loop_happy_path.html"
    run_id = "test-interleaved-1"
    writer = _make_writer_with_run(run_id)
    fake_llm = _FakeLLMClient([_done_response(fixture_url)])

    with Browser(playwright_browser=playwright_chromium) as browser:
        loop("task", browser, fake_llm, trace_writer=writer, run_id=run_id)

    next_s = writer.next_seq(run_id)
    obs = ObservationEvent(
        run_id=run_id,
        seq=next_s,
        ts="2024-01-01T00:00:00Z",
        step_id=None,
        url="https://example.com",
        title="Example",
        ax_tree_digest="[button Submit]",
        ax_fingerprint="fp123",
        screenshot_ref="/tmp/shot.png",
        viewport={"w": 1280, "h": 800},
    )
    writer.append_event(obs)

    rows = _all_rows(writer)
    plan_rows = [r for r in rows if r["kind"] == "plan"]
    obs_rows = [r for r in rows if r["kind"] == "observation"]
    assert plan_rows, "expected at least one plan row"
    assert obs_rows, "expected at least one observation row"
    plan_seq = plan_rows[0]["seq"]
    obs_seq = obs_rows[0]["seq"]
    assert plan_seq >= 1
    assert obs_seq >= 1
    assert plan_seq < obs_seq, f"plan_seq={plan_seq} not < obs_seq={obs_seq}"
    writer.close()


# ---------------------------------------------------------------------------
# locator_cache kwarg tests
# ---------------------------------------------------------------------------


def test_loop_accepts_locator_cache_kwarg(fixture_server, playwright_chromium):
    """loop() must accept locator_cache=None without raising TypeError.

    Also asserts that no LocateEvent rows are emitted when locator_cache=None —
    the cache emission path must be fully gated on the cache being provided.
    """
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    fake_llm = _FakeLLMClient([_done_response(fixture_url)])
    run_id = "test-kwarg-none"
    writer = _make_writer_with_run(run_id)

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop(
            "read the heading",
            browser,
            fake_llm,
            trace_writer=writer,
            run_id=run_id,
            locator_cache=None,
        )

    assert isinstance(result, RunResult)
    assert _locate_rows(writer) == [], (
        "no LocateEvent rows should be emitted when locator_cache=None"
    )
    writer.close()


def test_loop_locator_cache_none_skips_emission_on_read_dispatch(
    fixture_server, playwright_chromium
):
    fixture_url = f"{fixture_server}/drift/submit-form/v1/index.html"
    intent = "Submit button"
    run_id = "test-kwarg-none-with-read"
    writer = _make_writer_with_run(run_id)

    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
        _response_with_tool_call(_tool_call("read", {"intent": intent}, call_id="tc-2")),
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"ok": True},
                    "evidence": {"url": fixture_url, "text_snippet": "Submit"},
                },
                call_id="tc-3",
            )
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop(
            "click Submit",
            browser,
            fake_llm,
            trace_writer=writer,
            run_id=run_id,
            locator_cache=None,
        )

    assert result.status == "succeeded"
    assert _locate_rows(writer) == [], (
        "no LocateEvent rows should be emitted when locator_cache=None even on read dispatch"
    )
    writer.close()


def test_loop_forwards_cache_to_locate(fixture_server, playwright_chromium):
    """When loop() receives a LocatorCache, the read-path locate flow must write to it."""
    from agent.locator_cache import LocatorCache, _origin_from_url

    fixture_url = f"{fixture_server}/drift/submit-form/v1/index.html"
    intent = "Submit button"

    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
        _response_with_tool_call(_tool_call("read", {"intent": intent}, call_id="tc-2")),
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"ok": True},
                    "evidence": {"url": fixture_url, "text_snippet": "Submit"},
                },
                call_id="tc-3",
            )
        ),
    ]
    fake_llm = _FakeLLMClient(responses)
    cache = LocatorCache(path=":memory:")

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("click Submit", browser, fake_llm, locator_cache=cache)

    assert result.status == "succeeded"
    origin = _origin_from_url(fixture_url)
    entry = cache.get(origin=origin, intent=intent)
    assert entry is not None, (
        f"cache had no entry for (origin={origin!r}, intent={intent!r}) after the run"
    )
    assert entry.role == "button"
    cache.close()


# ---------------------------------------------------------------------------
# LocateEvent emission on the read-dispatch cache path
# ---------------------------------------------------------------------------


def _locate_rows(writer: TraceWriter) -> list[dict]:
    return [r for r in _all_rows(writer) if r.get("kind") == "locate"]


def test_loop_emits_locate_event_write_on_first_resolve(fixture_server, playwright_chromium):
    from agent.locator_cache import LocatorCache

    fixture_url = f"{fixture_server}/drift/submit-form/v1/index.html"
    intent = "Submit button"
    run_id = "test-emit-write"
    writer = _make_writer_with_run(run_id)
    cache = LocatorCache(path=":memory:")

    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
        _response_with_tool_call(_tool_call("read", {"intent": intent}, call_id="tc-2")),
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"ok": True},
                    "evidence": {"url": fixture_url, "text_snippet": "Submit"},
                },
                call_id="tc-3",
            )
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        loop(
            "click Submit",
            browser,
            fake_llm,
            trace_writer=writer,
            run_id=run_id,
            locator_cache=cache,
        )

    rows = _locate_rows(writer)
    write_rows = [r for r in rows if r.get("cache_action") == "write"]
    assert len(write_rows) == 1, (
        f"expected exactly one cache_action=write LocateEvent, got rows: {rows}"
    )
    assert write_rows[0]["intent"] == intent
    cache.close()
    writer.close()


def test_loop_emits_locate_event_invalidate_then_write_on_drift(
    fixture_server, playwright_chromium
):
    from agent.locator_cache import LocatorCache

    intent = "Submit button"
    cache = LocatorCache(path=":memory:")

    v1_url = f"{fixture_server}/drift/submit-form/v1/index.html"
    v2_url = f"{fixture_server}/drift/submit-form/v2/index.html"

    def _scripted_llm(target_url: str) -> _FakeLLMClient:
        return _FakeLLMClient(
            [
                _response_with_tool_call(_tool_call("goto", {"url": target_url}, call_id="tc-1")),
                _response_with_tool_call(_tool_call("read", {"intent": intent}, call_id="tc-2")),
                _response_with_tool_call(
                    _tool_call(
                        "done",
                        {
                            "result": {"ok": True},
                            "evidence": {"url": target_url, "text_snippet": "Submit"},
                        },
                        call_id="tc-3",
                    )
                ),
            ]
        )

    run_id_v1 = "test-emit-v1"
    writer_v1 = _make_writer_with_run(run_id_v1)
    with Browser(playwright_browser=playwright_chromium) as browser:
        loop(
            "click Submit",
            browser,
            _scripted_llm(v1_url),
            trace_writer=writer_v1,
            run_id=run_id_v1,
            locator_cache=cache,
        )
    writer_v1.close()

    run_id_v2 = "test-emit-v2"
    writer_v2 = _make_writer_with_run(run_id_v2)
    with Browser(playwright_browser=playwright_chromium) as browser:
        loop(
            "click Submit",
            browser,
            _scripted_llm(v2_url),
            trace_writer=writer_v2,
            run_id=run_id_v2,
            locator_cache=cache,
        )

    v2_rows = _locate_rows(writer_v2)
    cache_actions = [r.get("cache_action") for r in v2_rows]
    non_null_actions = [a for a in cache_actions if a is not None]
    assert non_null_actions == ["invalidate", "write"], (
        f"expected exactly one invalidate followed by one write on v2 run "
        f"(ignoring None ladder events), got non-null={non_null_actions} "
        f"full={cache_actions}"
    )
    cache.close()
    writer_v2.close()


def test_loop_emits_locate_event_read_on_cache_hit(fixture_server, playwright_chromium):
    """Second run on the same page must emit cache_action='read' + outcome='hit' + tier='cache'.

    Run 1 warms the cache (emits 'write').
    Run 2 probes the cache, finds a fingerprint match, and must emit 'read'/'hit'/'cache'
    without re-running the ladder.  No 'invalidate' row is expected on run 2.
    """
    from agent.locator_cache import LocatorCache

    intent = "Submit button"
    cache = LocatorCache(path=":memory:")
    fixture_url = f"{fixture_server}/drift/submit-form/v1/index.html"

    def _scripted_llm() -> _FakeLLMClient:
        return _FakeLLMClient(
            [
                _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
                _response_with_tool_call(_tool_call("read", {"intent": intent}, call_id="tc-2")),
                _response_with_tool_call(
                    _tool_call(
                        "done",
                        {
                            "result": {"ok": True},
                            "evidence": {"url": fixture_url, "text_snippet": "Submit"},
                        },
                        call_id="tc-3",
                    )
                ),
            ]
        )

    # Run 1: warm the cache — must emit cache_action="write"
    run_id_1 = "test-cache-hit-run1"
    writer_1 = _make_writer_with_run(run_id_1)
    with Browser(playwright_browser=playwright_chromium) as browser:
        loop(
            "click Submit",
            browser,
            _scripted_llm(),
            trace_writer=writer_1,
            run_id=run_id_1,
            locator_cache=cache,
        )
    rows_1 = _locate_rows(writer_1)
    assert any(r.get("cache_action") == "write" for r in rows_1), (
        f"run 1 must emit a write event to warm the cache, got rows: {rows_1}"
    )
    writer_1.close()

    # Run 2: probe the same page — must find a fingerprint match and emit cache_action="read"
    run_id_2 = "test-cache-hit-run2"
    writer_2 = _make_writer_with_run(run_id_2)
    with Browser(playwright_browser=playwright_chromium) as browser:
        loop(
            "click Submit",
            browser,
            _scripted_llm(),
            trace_writer=writer_2,
            run_id=run_id_2,
            locator_cache=cache,
        )

    rows_2 = _locate_rows(writer_2)
    actions_2 = [r.get("cache_action") for r in rows_2]

    # The fingerprint from the same fixture must be stable across two page loads.
    # If this assertion fails, that is a real AX non-determinism bug — do not weaken it.
    assert actions_2 == ["read"], (
        f"expected exactly one cache_action='read' row on run 2 with no writes/invalidates, "
        f"got actions: {actions_2}, all rows: {rows_2}"
    )
    read_row = rows_2[0]
    assert read_row.get("outcome") == "hit"
    assert read_row.get("tier") == "cache"
    assert read_row.get("intent") == intent

    cache.close()
    writer_2.close()


# ---------------------------------------------------------------------------
# step_id threading tests (tasks 1.1–1.4 and 2.1–2.3)
# ---------------------------------------------------------------------------


def test_loop_with_trace_writer_initial_plan_event_step_id(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    run_id = "test-step-id-initial"
    writer = _make_writer_with_run(run_id)
    fake_llm = _FakeLLMClient([_done_response(fixture_url)])

    with Browser(playwright_browser=playwright_chromium) as browser:
        loop("task", browser, fake_llm, trace_writer=writer, run_id=run_id)

    plan_rows = _plan_rows(writer)
    initial_rows = [r for r in plan_rows if r.get("reason") == "initial"]
    assert len(initial_rows) >= 1
    assert initial_rows[0]["step_id"] == f"{run_id}:step-1"
    writer.close()


def test_loop_with_trace_writer_replan_event_step_id(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/index.html"
    run_id = "test-step-id-replan"
    writer = _make_writer_with_run(run_id)
    fake_llm = _HaltReplanLLM(fixture_url)

    with Browser(playwright_browser=playwright_chromium) as browser:
        loop(
            "click the Submit button",
            browser,
            fake_llm,
            max_steps=10,
            trace_writer=writer,
            run_id=run_id,
        )

    plan_rows = _plan_rows(writer)
    replan_rows = [r for r in plan_rows if r.get("reason") == "replan"]
    assert len(replan_rows) >= 1
    step_id = replan_rows[0]["step_id"]
    assert step_id is not None
    assert step_id.startswith(f"{run_id}:step-")
    step_num = int(step_id.split(":step-")[1])
    assert step_num >= 2
    writer.close()


def test_loop_in_memory_events_plan_event_step_id_with_run_id(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    run_id = "test-run"
    events: list = []
    fake_llm = _FakeLLMClient([_done_response(fixture_url)])

    with Browser(playwright_browser=playwright_chromium) as browser:
        loop("task", browser, fake_llm, events=events, run_id=run_id)

    plan_objects = [e for e in events if hasattr(e, "kind") and e.kind == "plan"]
    assert len(plan_objects) >= 1
    assert plan_objects[0].step_id == "test-run:step-1"


def test_loop_in_memory_events_plan_event_step_id_no_run_id(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    events: list = []
    fake_llm = _FakeLLMClient([_done_response(fixture_url)])

    with Browser(playwright_browser=playwright_chromium) as browser:
        loop("task", browser, fake_llm, events=events)

    plan_objects = [e for e in events if hasattr(e, "kind") and e.kind == "plan"]
    assert len(plan_objects) >= 1
    assert plan_objects[0].step_id is None


def test_loop_emit_locate_event_step_id_on_cache_write(fixture_server, playwright_chromium):
    from agent.locator_cache import LocatorCache

    fixture_url = f"{fixture_server}/drift/submit-form/v1/index.html"
    intent = "Submit button"
    run_id = "test-locate-step-id-write"
    writer = _make_writer_with_run(run_id)
    cache = LocatorCache(path=":memory:")

    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
        _response_with_tool_call(_tool_call("read", {"intent": intent}, call_id="tc-2")),
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"ok": True},
                    "evidence": {"url": fixture_url, "text_snippet": "Submit"},
                },
                call_id="tc-3",
            )
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        loop(
            "click Submit",
            browser,
            fake_llm,
            trace_writer=writer,
            run_id=run_id,
            locator_cache=cache,
        )

    rows = _locate_rows(writer)
    write_rows = [r for r in rows if r.get("cache_action") == "write"]
    assert len(write_rows) >= 1
    assert write_rows[0]["step_id"] == f"{run_id}:step-2"
    cache.close()
    writer.close()


def test_loop_emit_locate_event_step_id_on_cache_invalidate(fixture_server, playwright_chromium):
    from agent.locator_cache import LocatorCache

    intent = "Submit button"
    cache = LocatorCache(path=":memory:")

    v1_url = f"{fixture_server}/drift/submit-form/v1/index.html"
    v2_url = f"{fixture_server}/drift/submit-form/v2/index.html"

    def _scripted_llm(target_url: str) -> _FakeLLMClient:
        return _FakeLLMClient(
            [
                _response_with_tool_call(_tool_call("goto", {"url": target_url}, call_id="tc-1")),
                _response_with_tool_call(_tool_call("read", {"intent": intent}, call_id="tc-2")),
                _response_with_tool_call(
                    _tool_call(
                        "done",
                        {
                            "result": {"ok": True},
                            "evidence": {"url": target_url, "text_snippet": "Submit"},
                        },
                        call_id="tc-3",
                    )
                ),
            ]
        )

    run_id_v1 = "test-locate-invalidate-v1"
    writer_v1 = _make_writer_with_run(run_id_v1)
    with Browser(playwright_browser=playwright_chromium) as browser:
        loop(
            "click Submit",
            browser,
            _scripted_llm(v1_url),
            trace_writer=writer_v1,
            run_id=run_id_v1,
            locator_cache=cache,
        )
    writer_v1.close()

    run_id_v2 = "test-locate-invalidate-v2"
    writer_v2 = _make_writer_with_run(run_id_v2)
    with Browser(playwright_browser=playwright_chromium) as browser:
        loop(
            "click Submit",
            browser,
            _scripted_llm(v2_url),
            trace_writer=writer_v2,
            run_id=run_id_v2,
            locator_cache=cache,
        )

    v2_rows = _locate_rows(writer_v2)
    invalidate_rows = [r for r in v2_rows if r.get("cache_action") == "invalidate"]
    write_rows = [r for r in v2_rows if r.get("cache_action") == "write"]
    assert len(invalidate_rows) >= 1
    assert len(write_rows) >= 1
    step_id = invalidate_rows[0]["step_id"]
    assert step_id is not None
    assert step_id.startswith(f"{run_id_v2}:step-")
    assert write_rows[0]["step_id"] == step_id
    cache.close()
    writer_v2.close()


def test_loop_emit_locate_event_step_id_on_cache_hit(fixture_server, playwright_chromium):
    from agent.locator_cache import LocatorCache

    intent = "Submit button"
    cache = LocatorCache(path=":memory:")
    fixture_url = f"{fixture_server}/drift/submit-form/v1/index.html"

    def _scripted_llm() -> _FakeLLMClient:
        return _FakeLLMClient(
            [
                _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
                _response_with_tool_call(_tool_call("read", {"intent": intent}, call_id="tc-2")),
                _response_with_tool_call(
                    _tool_call(
                        "done",
                        {
                            "result": {"ok": True},
                            "evidence": {"url": fixture_url, "text_snippet": "Submit"},
                        },
                        call_id="tc-3",
                    )
                ),
            ]
        )

    run_id_1 = "test-locate-hit-run1"
    writer_1 = _make_writer_with_run(run_id_1)
    with Browser(playwright_browser=playwright_chromium) as browser:
        loop(
            "click Submit",
            browser,
            _scripted_llm(),
            trace_writer=writer_1,
            run_id=run_id_1,
            locator_cache=cache,
        )
    writer_1.close()

    run_id_2 = "test-locate-hit-run2"
    writer_2 = _make_writer_with_run(run_id_2)
    with Browser(playwright_browser=playwright_chromium) as browser:
        loop(
            "click Submit",
            browser,
            _scripted_llm(),
            trace_writer=writer_2,
            run_id=run_id_2,
            locator_cache=cache,
        )

    rows_2 = _locate_rows(writer_2)
    read_rows = [r for r in rows_2 if r.get("cache_action") == "read" and r.get("outcome") == "hit"]
    assert len(read_rows) >= 1
    step_id = read_rows[0]["step_id"]
    assert step_id is not None
    assert step_id.startswith(f"{run_id_2}:step-")
    cache.close()
    writer_2.close()


# ---------------------------------------------------------------------------
# _emit_locate_event return-value unit tests
# ---------------------------------------------------------------------------


def test_emit_locate_event_returns_allocated_seq():
    from agent.loop import _emit_locate_event

    run_id = "emit-locate-ret-1"
    writer = _make_writer_with_run(run_id)

    result = _emit_locate_event(
        trace_writer=writer,
        run_id=run_id,
        intent="Submit button",
        tier="L1_ax",
        outcome="miss",
        cache_action=None,
        chosen=None,
        step_id=None,
    )

    events = list(writer.iter_events(run_id))
    assert len(events) == 1
    assert result == events[0].seq

    result_none = _emit_locate_event(
        trace_writer=None,
        run_id=None,
        intent="Submit button",
        tier="L1_ax",
        outcome="miss",
        cache_action=None,
        chosen=None,
        step_id=None,
    )
    assert result_none is None

    writer.close()


# ---------------------------------------------------------------------------
# _emit_supervisor_event unit tests
# ---------------------------------------------------------------------------


def test_emit_supervisor_event_noop_when_trace_writer_none():
    from agent.locate import LocatorMiss
    from agent.loop import _emit_supervisor_event
    from agent.supervisor import EscalationDecision

    run_id = "sv-noop-1"
    writer = _make_writer_with_run(run_id)

    decision = EscalationDecision(next_tier="L2_dom", policy="next_tier", attempt=1)
    miss = LocatorMiss(reason="zero_matches", match_count=0)
    _emit_supervisor_event(
        trace_writer=None,
        run_id=None,
        decision=decision,
        miss=miss,
        trigger_event_seq=1,
        step_id=None,
    )

    assert list(writer.iter_events(run_id)) == []
    writer.close()


def test_emit_supervisor_event_writes_correct_fields():
    from agent.locate import LocatorMiss
    from agent.loop import _emit_supervisor_event
    from agent.supervisor import EscalationDecision

    run_id = "sv-test-1"
    writer = _make_writer_with_run(run_id)

    locate_event = LocateEvent(
        run_id=run_id,
        seq=1,
        ts="2024-01-01T00:00:00+00:00",
        step_id="sv-test-1:step-2",
        intent="Submit button",
        tier="L1_ax",
        outcome="miss",
        candidates=[],
        chosen=None,
        cache_action=None,
        ms=0,
    )
    writer.append_event(locate_event)

    decision = EscalationDecision(next_tier="L2_dom", policy="next_tier", attempt=1)
    miss = LocatorMiss(reason="zero_matches", match_count=0)
    _emit_supervisor_event(
        trace_writer=writer,
        run_id=run_id,
        decision=decision,
        miss=miss,
        trigger_event_seq=1,
        step_id="sv-test-1:step-2",
    )

    events = list(writer.iter_events(run_id))
    sv_events = [e for e in events if isinstance(e, SupervisorEvent)]
    assert len(sv_events) == 1
    ev = sv_events[0]
    assert ev.policy == "next_tier"
    assert ev.classified_as == "LocatorMiss"
    assert ev.trigger_event_seq == 1
    assert ev.attempt == 1
    assert ev.step_id == "sv-test-1:step-2"
    writer.close()


def test_emit_supervisor_event_maps_ambiguous_reason():
    from agent.locate import LocatorMiss
    from agent.loop import _emit_supervisor_event
    from agent.supervisor import EscalationDecision

    run_id = "sv-test-2"
    writer = _make_writer_with_run(run_id)

    locate_event = LocateEvent(
        run_id=run_id,
        seq=1,
        ts="2024-01-01T00:00:00+00:00",
        step_id=None,
        intent="Save button",
        tier="L1_ax",
        outcome="ambiguous",
        candidates=[],
        chosen=None,
        cache_action=None,
        ms=0,
    )
    writer.append_event(locate_event)

    decision = EscalationDecision(next_tier=None, policy="halt", attempt=1)
    miss = LocatorMiss(reason="ambiguous", match_count=3)
    _emit_supervisor_event(
        trace_writer=writer,
        run_id=run_id,
        decision=decision,
        miss=miss,
        trigger_event_seq=1,
        step_id=None,
    )

    events = list(writer.iter_events(run_id))
    sv_events = [e for e in events if isinstance(e, SupervisorEvent)]
    assert len(sv_events) == 1
    assert sv_events[0].classified_as == "Ambiguous"
    writer.close()


def test_emit_supervisor_event_maps_vision_miss_reason():
    from agent.locate import LocatorMiss
    from agent.loop import _emit_supervisor_event
    from agent.supervisor import EscalationDecision

    run_id = "sv-test-3"
    writer = _make_writer_with_run(run_id)

    locate_event = LocateEvent(
        run_id=run_id,
        seq=1,
        ts="2024-01-01T00:00:00+00:00",
        step_id=None,
        intent="Submit button",
        tier="L4_vision",
        outcome="miss",
        candidates=[],
        chosen=None,
        cache_action=None,
        ms=0,
    )
    writer.append_event(locate_event)

    decision = EscalationDecision(next_tier=None, policy="halt", attempt=1)
    miss = LocatorMiss(reason="vision_miss", match_count=0)
    _emit_supervisor_event(
        trace_writer=writer,
        run_id=run_id,
        decision=decision,
        miss=miss,
        trigger_event_seq=1,
        step_id=None,
    )

    events = list(writer.iter_events(run_id))
    sv_events = [e for e in events if isinstance(e, SupervisorEvent)]
    assert len(sv_events) == 1
    assert sv_events[0].classified_as == "LocatorMiss"
    writer.close()


# ---------------------------------------------------------------------------
# _locate_via_ladder trace emission unit tests
# ---------------------------------------------------------------------------


def _make_mock_supervisor_next_tier(next_tier: str = "L2_dom"):
    from agent.locate import LocatorMiss
    from agent.supervisor import EscalationDecision, Supervisor

    class _AlwaysNextTier(Supervisor):
        def handle(self, miss: LocatorMiss, *, current_tier: str) -> EscalationDecision:
            decision = EscalationDecision(next_tier=next_tier, policy="next_tier", attempt=1)
            self.last_policy = decision.policy
            return decision

    return _AlwaysNextTier()


def test_locate_via_ladder_l1_miss_l2_hit_emits_three_events(fixture_server, playwright_chromium):
    from agent.loop import _locate_via_ladder

    run_id = "ladder-test-1"
    writer = _make_writer_with_run(run_id)
    supervisor = _make_mock_supervisor_next_tier()

    fixture_url = f"{fixture_server}/correction_l1_miss.html"
    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        result = _locate_via_ladder(
            browser._page,
            "Submit button",
            supervisor,
            trace_writer=writer,
            run_id=run_id,
            step_id="ladder-test-1:step-1",
        )

    assert result is not None

    events = list(writer.iter_events(run_id))
    locate_events = [e for e in events if isinstance(e, LocateEvent)]
    sv_events = [e for e in events if isinstance(e, SupervisorEvent)]

    assert len(locate_events) >= 2
    l1_miss = next((e for e in locate_events if e.tier == "L1_ax" and e.outcome == "miss"), None)
    l2_hit = next((e for e in locate_events if e.tier == "L2_dom" and e.outcome == "hit"), None)
    assert l1_miss is not None, "expected L1_ax miss LocateEvent"
    assert l2_hit is not None, "expected L2_dom hit LocateEvent"

    assert len(sv_events) == 1
    sv = sv_events[0]
    assert sv.policy == "next_tier"
    assert sv.trigger_event_seq == l1_miss.seq

    seqs = [e.seq for e in events]
    assert seqs == sorted(set(seqs)), "seqs must be strictly increasing"
    writer.close()


def test_locate_via_ladder_l1_miss_l2_miss_emits_events_and_raises(
    playwright_chromium,
):
    from agent.locate import LocatorMiss
    from agent.loop import _locate_via_ladder

    run_id = "ladder-test-2"
    writer = _make_writer_with_run(run_id)
    supervisor = _make_mock_supervisor_next_tier()

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser._page.set_content("<html><body><h1>Empty</h1></body></html>")
        with pytest.raises(LocatorMiss):
            _locate_via_ladder(
                browser._page,
                "Nonexistent button",
                supervisor,
                trace_writer=writer,
                run_id=run_id,
                step_id=None,
            )

    events = list(writer.iter_events(run_id))
    locate_events = [e for e in events if isinstance(e, LocateEvent)]
    sv_events = [e for e in events if isinstance(e, SupervisorEvent)]

    l1_miss = next((e for e in locate_events if e.tier == "L1_ax" and e.outcome == "miss"), None)
    l2_miss = next((e for e in locate_events if e.tier == "L2_dom" and e.outcome == "miss"), None)
    assert l1_miss is not None, "expected L1_ax miss LocateEvent"
    assert l2_miss is not None, "expected L2_dom miss LocateEvent"
    assert len(sv_events) == 1
    sv = sv_events[0]
    assert l1_miss.seq < sv.seq < l2_miss.seq, (
        "expected ordering: L1_ax miss → SupervisorEvent → L2_dom miss"
    )
    assert sv.trigger_event_seq == l1_miss.seq
    writer.close()


def test_locate_via_ladder_no_trace_kwargs_no_emission(fixture_server, playwright_chromium):
    from agent.loop import _locate_via_ladder

    supervisor = _make_mock_supervisor_next_tier()
    fixture_url = f"{fixture_server}/correction_l1_miss.html"

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        result = _locate_via_ladder(browser._page, "Submit button", supervisor)

    assert result is not None
    assert result.tier == "L2_dom"


# ---------------------------------------------------------------------------
# Integration test: real loop on correction_l1_miss produces escalation
# ---------------------------------------------------------------------------


def test_real_loop_correction_l1_miss_produces_escalation(fixture_server, playwright_chromium):
    from scripts.eval import _aggregate_diagnostics

    fixture_url = f"{fixture_server}/correction_l1_miss.html"
    run_id = "integ-l1-miss-1"
    writer = _make_writer_with_run(run_id)

    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
        _response_with_tool_call(_tool_call("read", {"intent": "Submit button"}, call_id="tc-2")),
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"ok": True},
                    "evidence": {"url": fixture_url, "text_snippet": "Submit"},
                },
                call_id="tc-3",
            )
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        loop("submit the form", browser, fake_llm, trace_writer=writer, run_id=run_id)

    events, escalations, _replans, _cache = _aggregate_diagnostics(writer, run_id)
    assert len(escalations) >= 1, (
        f"expected at least one escalation from L1 miss on correction_l1_miss fixture, "
        f"got escalations={escalations}"
    )
    l1_escalation = next((e for e in escalations if e["from_tier"] == "L1_ax"), None)
    assert l1_escalation is not None, (
        f"expected from_tier=L1_ax in escalations, got {[e['from_tier'] for e in escalations]}"
    )
    assert l1_escalation["to_tier"] == "L2_dom", (
        f"expected to_tier=L2_dom for the L1_ax escalation, got {l1_escalation['to_tier']}"
    )
    l2_locate = next(
        (e for e in events if isinstance(e, LocateEvent) and e.tier == "L2_dom"),
        None,
    )
    assert l2_locate is not None, "expected at least one LocateEvent(tier='L2_dom') in the trace"
    writer.close()


# ---------------------------------------------------------------------------
# Click tool: TOOLS list includes click entry
# ---------------------------------------------------------------------------


def test_tools_list_includes_click():
    from agent.loop import TOOLS

    click_entry = next((t for t in TOOLS if t["function"]["name"] == "click"), None)
    assert click_entry is not None, "TOOLS must contain an entry with function.name == 'click'"
    props = click_entry["function"]["parameters"]["properties"]
    assert "intent" in props, "click entry must have 'intent' in parameters.properties"
    assert props["intent"]["type"] == "string", "click 'intent' parameter must be type 'string'"
    required = click_entry["function"]["parameters"]["required"]
    assert "intent" in required, "'intent' must appear in click's parameters.required"


# ---------------------------------------------------------------------------
# Click tool: LLM calls click → ActEvent(outcome="ok") emitted, run succeeds
# ---------------------------------------------------------------------------


def test_loop_click_to_done(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_click_submit.html"

    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
        _response_with_tool_call(_tool_call("click", {"intent": "Submit button"}, call_id="tc-2")),
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"clicked": True},
                    "evidence": {"url": fixture_url, "text_snippet": "Submit"},
                },
                call_id="tc-3",
            )
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    run_id = "test-click-to-done"
    writer = _make_writer_with_run(run_id)

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("click Submit", browser, fake_llm, trace_writer=writer, run_id=run_id)

    assert result.status == "succeeded"
    assert result.steps <= 4

    from agent.trace import ActEvent

    events = list(writer.iter_events(run_id))
    act_events = [e for e in events if isinstance(e, ActEvent)]
    assert len(act_events) >= 1, "expected at least one ActEvent"
    click_act = next((e for e in act_events if e.tool == "click"), None)
    assert click_act is not None, "expected ActEvent with tool='click'"
    assert click_act.outcome == "ok", f"expected outcome='ok', got {click_act.outcome!r}"
    assert click_act.args == {"intent": "Submit button"}
    writer.close()


# ---------------------------------------------------------------------------
# Click tool: navigation after click → ActEvent(outcome="nav")
# ---------------------------------------------------------------------------


def test_loop_click_outcome_nav(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_click_nav.html"
    dest_url = f"{fixture_server}/loop_happy_path.html"

    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
        _response_with_tool_call(_tool_call("click", {"intent": "Go button"}, call_id="tc-2")),
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"navigated": True},
                    "evidence": {"url": dest_url, "text_snippet": "Hello"},
                },
                call_id="tc-3",
            )
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    run_id = "test-click-nav"
    writer = _make_writer_with_run(run_id)

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("click Go", browser, fake_llm, trace_writer=writer, run_id=run_id)

    from agent.trace import ActEvent

    events = list(writer.iter_events(run_id))
    act_events = [e for e in events if isinstance(e, ActEvent) and e.tool == "click"]
    assert len(act_events) >= 1, "expected at least one ActEvent with tool='click'"
    assert act_events[0].outcome == "nav", (
        f"expected outcome='nav' after navigation, got {act_events[0].outcome!r}"
    )
    assert result.status == "succeeded"
    writer.close()


# ---------------------------------------------------------------------------
# Click tool: L1 miss → supervisor escalates to L2 → SupervisorEvent(policy="next_tier")
# ---------------------------------------------------------------------------


def test_loop_click_l1_miss_supervisor_escalation(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/correction_l1_miss.html"

    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
        _response_with_tool_call(_tool_call("click", {"intent": "Submit button"}, call_id="tc-2")),
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"clicked": True},
                    "evidence": {"url": fixture_url, "text_snippet": "Submit"},
                },
                call_id="tc-3",
            )
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    run_id = "test-click-l1-miss"
    writer = _make_writer_with_run(run_id)

    with Browser(playwright_browser=playwright_chromium) as browser:
        loop("click the Submit button", browser, fake_llm, trace_writer=writer, run_id=run_id)

    events = list(writer.iter_events(run_id))
    supervisor_events = [e for e in events if isinstance(e, SupervisorEvent)]
    assert len(supervisor_events) >= 1, "expected at least one SupervisorEvent"
    next_tier_event = next((e for e in supervisor_events if e.policy == "next_tier"), None)
    policies = [e.policy for e in supervisor_events]
    assert next_tier_event is not None, (
        f"expected SupervisorEvent(policy='next_tier'), got policies={policies}"
    )
    act_events = [e for e in events if isinstance(e, ActEvent) and e.tool == "click"]
    assert len(act_events) == 1, (
        f"expected exactly one click ActEvent after L2 escalation, got {len(act_events)}"
    )
    outcome = act_events[0].outcome
    assert outcome in {"ok", "nav"}, (
        f"expected click ActEvent.outcome in {{ok, nav}} after escalation, got {outcome!r}"
    )
    writer.close()


# ---------------------------------------------------------------------------
# Click tool: invalid intent (IntentParseError) returns error string, loop continues
# ---------------------------------------------------------------------------


def test_loop_click_invalid_intent_returns_error_string_loop_continues(
    fixture_server, playwright_chromium
):
    fixture_url = f"{fixture_server}/loop_click_submit.html"

    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
        _response_with_tool_call(
            _tool_call("click", {"intent": "the full page content"}, call_id="tc-2")
        ),
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"done": True},
                    "evidence": {"url": fixture_url, "text_snippet": "Submit"},
                },
                call_id="tc-3",
            )
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("click submit", browser, fake_llm, max_steps=10)

    assert result.status == "succeeded", (
        f"expected loop to continue past IntentParseError and reach done, got {result.status!r}"
    )
    assert result.steps <= 4


# ---------------------------------------------------------------------------
# Read tool: invalid intent (IntentParseError) returns error string, loop continues
# ---------------------------------------------------------------------------


def test_loop_read_invalid_intent_returns_error_string_loop_continues(
    fixture_server, playwright_chromium
):
    fixture_url = f"{fixture_server}/loop_click_submit.html"

    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
        _response_with_tool_call(
            _tool_call("read", {"intent": "the full page content"}, call_id="tc-2")
        ),
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"done": True},
                    "evidence": {"url": fixture_url, "text_snippet": "Submit"},
                },
                call_id="tc-3",
            )
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("read the page", browser, fake_llm, max_steps=10)

    assert result.status == "succeeded", (
        "expected loop to continue past read IntentParseError and reach done, "
        f"got {result.status!r}"
    )
    assert result.steps <= 4


# ---------------------------------------------------------------------------
# Task 2: click with slow navigation — wait_for_load_state timeout → outcome=nav
# ---------------------------------------------------------------------------


def _make_fake_browser_for_click(
    selector: str,
    url_before: str,
    url_after: str,
    click_raises: Exception | None = None,
    wait_raises: Exception | None = None,
):
    import types

    from agent.locate import LocateResult

    locate_result = LocateResult(
        tier="L1_ax",
        role="button",
        name="Submit",
        selector=selector,
        ax_fingerprint="fp-stub",
        confidence=1.0,
        coords=None,
    )

    _url_holder = [url_before]

    class _StubLocator:
        def click(self, *, timeout):
            if click_raises is not None:
                raise click_raises
            _url_holder[0] = url_after

    class _StubPage:
        @property
        def url(self):
            return _url_holder[0]

        def locator(self, sel):
            return _StubLocator()

        def wait_for_load_state(self, state, *, timeout):
            if wait_raises is not None:
                raise wait_raises

    fake_page = _StubPage()
    fake_browser = types.SimpleNamespace(_page=fake_page)
    return fake_browser, locate_result


def _open_click_writer(run_id: str) -> TraceWriter:
    writer = TraceWriter(":memory:")
    writer.open_run(
        Run(
            run_id=run_id,
            task="t",
            expect_schema=None,
            budget=RunBudget(steps=5, usd=1.0, seconds=60),
            llm=RunLLM(base_url="", model="", temperature=0.0, seed=None),
            agent_version="test",
            started_at="2024-01-01T00:00:00Z",
            ended_at=None,
            status=None,
            final=None,
            totals=None,
        )
    )
    return writer


def test_loop_click_slow_nav_wait_load_timeout_still_classifies_as_nav_or_ok(monkeypatch):
    import playwright.sync_api as pw_api

    from agent.loop import _dispatch
    from agent.supervisor import Supervisor

    selector = "button[type=submit]"
    url_before = "http://example.com/form"
    url_after = "http://example.com/thanks"

    wait_timeout_err = pw_api.TimeoutError("wait_for_load_state timed out")
    fake_browser, locate_result = _make_fake_browser_for_click(
        selector, url_before, url_after, wait_raises=wait_timeout_err
    )

    monkeypatch.setattr(
        "agent.loop._locate_or_error_msg",
        lambda *_args, **_kwargs: locate_result,
    )

    run_id = "unit-slow-nav"
    writer = _open_click_writer(run_id)

    result_str = _dispatch(
        "click",
        {"intent": "Submit button"},
        fake_browser,
        Supervisor(),
        trace_writer=writer,
        run_id=run_id,
        step_id=f"{run_id}:step-1",
    )

    act_events = [e for e in writer.iter_events(run_id) if isinstance(e, ActEvent)]
    assert len(act_events) == 1
    assert act_events[0].outcome in {"nav", "ok"}, (
        f"expected nav (URL changed) or ok, got {act_events[0].outcome!r}; result={result_str!r}"
    )
    assert act_events[0].outcome == "nav", (
        f"URL changed from {url_before!r} to {url_after!r} — expected outcome=nav, "
        f"got {act_events[0].outcome!r}"
    )
    writer.close()


# ---------------------------------------------------------------------------
# Task 3: click raises TimeoutError → outcome=timeout; raises Error → outcome=error
# ---------------------------------------------------------------------------


def test_loop_click_playwright_timeout_yields_outcome_timeout(monkeypatch):
    import playwright.sync_api as pw_api

    from agent.loop import _dispatch
    from agent.supervisor import Supervisor

    selector = "button[type=submit]"
    click_err = pw_api.TimeoutError("click timed out")
    fake_browser, locate_result = _make_fake_browser_for_click(
        selector, "http://example.com/", "http://example.com/", click_raises=click_err
    )

    monkeypatch.setattr(
        "agent.loop._locate_or_error_msg",
        lambda *_args, **_kwargs: locate_result,
    )

    run_id = "unit-timeout"
    writer = _open_click_writer(run_id)

    result_str = _dispatch(
        "click",
        {"intent": "Submit button"},
        fake_browser,
        Supervisor(),
        trace_writer=writer,
        run_id=run_id,
        step_id=f"{run_id}:step-1",
    )

    act_events = [e for e in writer.iter_events(run_id) if isinstance(e, ActEvent)]
    assert len(act_events) == 1
    assert act_events[0].outcome == "timeout", (
        f"expected outcome=timeout, got {act_events[0].outcome!r}"
    )
    assert result_str.startswith("Error: click timeout"), (
        f"expected tool result to start with 'Error: click timeout', got {result_str!r}"
    )
    writer.close()


def test_loop_click_playwright_error_yields_outcome_error(monkeypatch):
    import playwright.sync_api as pw_api

    from agent.loop import _dispatch
    from agent.supervisor import Supervisor

    selector = "button[type=submit]"
    click_err = pw_api.Error("element not interactable")
    fake_browser, locate_result = _make_fake_browser_for_click(
        selector, "http://example.com/", "http://example.com/", click_raises=click_err
    )

    monkeypatch.setattr(
        "agent.loop._locate_or_error_msg",
        lambda *_args, **_kwargs: locate_result,
    )

    run_id = "unit-error"
    writer = _open_click_writer(run_id)

    result_str = _dispatch(
        "click",
        {"intent": "Submit button"},
        fake_browser,
        Supervisor(),
        trace_writer=writer,
        run_id=run_id,
        step_id=f"{run_id}:step-1",
    )

    act_events = [e for e in writer.iter_events(run_id) if isinstance(e, ActEvent)]
    assert len(act_events) == 1
    assert act_events[0].outcome == "error", (
        f"expected outcome=error, got {act_events[0].outcome!r}"
    )
    assert result_str.startswith("Error: click error"), (
        f"expected tool result to start with 'Error: click error', got {result_str!r}"
    )


# ---------------------------------------------------------------------------
# Type tool: TOOLS list includes type entry with intent and text parameters
# ---------------------------------------------------------------------------


def test_tools_list_includes_type():
    from agent.loop import TOOLS

    type_entry = next((t for t in TOOLS if t["function"]["name"] == "type"), None)
    assert type_entry is not None, "TOOLS must contain an entry with function.name == 'type'"
    props = type_entry["function"]["parameters"]["properties"]
    assert "intent" in props, "type entry must have 'intent' in parameters.properties"
    assert props["intent"]["type"] == "string", "type 'intent' parameter must be type 'string'"
    assert "text" in props, "type entry must have 'text' in parameters.properties"
    assert props["text"]["type"] == "string", "type 'text' parameter must be type 'string'"
    required = type_entry["function"]["parameters"]["required"]
    assert "intent" in required, "'intent' must appear in type's parameters.required"
    assert "text" in required, "'text' must appear in type's parameters.required"


# ---------------------------------------------------------------------------
# Type tool: LLM calls type → ActEvent(outcome="ok") emitted, run succeeds
# ---------------------------------------------------------------------------


def test_loop_type_fills_textbox(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_type_textbox.html"

    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
        _response_with_tool_call(
            _tool_call(
                "type",
                {"intent": "Email textbox", "text": "hello@example.com"},
                call_id="tc-2",
            )
        ),
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"typed": True},
                    "evidence": {"url": fixture_url, "text_snippet": "Type Textbox"},
                },
                call_id="tc-3",
            )
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    run_id = "test-type-fills-textbox"
    writer = _make_writer_with_run(run_id)

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("fill email", browser, fake_llm, trace_writer=writer, run_id=run_id)
        filled_value = browser._page.locator("#email").input_value()

    assert result.status == "succeeded"
    assert result.steps <= 4
    assert filled_value == "hello@example.com", (
        f"expected textbox to contain typed text, got {filled_value!r}"
    )

    act_events = [e for e in writer.iter_events(run_id) if isinstance(e, ActEvent)]
    type_act = next((e for e in act_events if e.tool == "type"), None)
    assert type_act is not None, "expected ActEvent with tool='type'"
    assert type_act.outcome == "ok", f"expected outcome='ok', got {type_act.outcome!r}"
    assert type_act.args["intent"] == "Email textbox"
    writer.close()


# ---------------------------------------------------------------------------
# Type tool: L1 miss (all tiers miss) → tool error returned, loop continues
# ---------------------------------------------------------------------------


def test_loop_type_l1_miss_returns_tool_error_loop_continues(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/loop_type_textbox.html"

    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
        _response_with_tool_call(
            _tool_call(
                "type",
                {"intent": "Nonexistent textbox", "text": "foo"},
                call_id="tc-2",
            )
        ),
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"done": True},
                    "evidence": {"url": fixture_url, "text_snippet": "Type Textbox"},
                },
                call_id="tc-3",
            )
        ),
    ]
    fake_llm = _FakeLLMClient(responses)

    run_id = "test-type-l1-miss"
    writer = _make_writer_with_run(run_id)

    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop(
            "fill nonexistent", browser, fake_llm, max_steps=10, trace_writer=writer, run_id=run_id
        )

    assert result.status == "succeeded", (
        f"expected loop to continue past type miss and reach done, got {result.status!r}"
    )
    assert result.steps <= 4

    events = list(writer.iter_events(run_id))
    type_act_events = [e for e in events if isinstance(e, ActEvent) and e.tool == "type"]
    assert len(type_act_events) == 0, (
        f"expected zero type ActEvents (locate-miss path returns before emit), "
        f"got {[(e.tool, e.outcome) for e in type_act_events]}"
    )
    writer.close()


# ---------------------------------------------------------------------------
# Type tool: Locator.fill raises TimeoutError → outcome=timeout, loop continues
# ---------------------------------------------------------------------------


def _make_fake_browser_for_type(
    selector: str,
    fill_raises: Exception | None = None,
):
    import types

    from agent.locate import LocateResult

    locate_result = LocateResult(
        tier="L2_dom",
        role="textbox",
        name="Email",
        selector=selector,
        ax_fingerprint="fp-stub",
        confidence=1.0,
        coords=None,
    )

    class _StubLocator:
        def __init__(self):
            self.fill_calls: list[dict] = []

        def fill(self, text, *, timeout):
            self.fill_calls.append({"text": text, "timeout": timeout})
            if fill_raises is not None:
                raise fill_raises

    stub_locator = _StubLocator()

    class _StubPage:
        @property
        def url(self):
            return "http://example.com/"

        def locator(self, sel):
            assert sel == locate_result.selector, (
                f"expected page.locator({locate_result.selector!r}), got {sel!r}"
            )
            return stub_locator

    fake_page = _StubPage()
    fake_browser = types.SimpleNamespace(_page=fake_page)
    return fake_browser, locate_result, stub_locator


def test_loop_type_playwright_timeout_yields_outcome_timeout(monkeypatch):
    import playwright.sync_api as pw_api

    from agent.loop import _dispatch
    from agent.supervisor import Supervisor

    selector = "input#email"
    fill_err = pw_api.TimeoutError("fill timed out")
    fake_browser, locate_result, stub_locator = _make_fake_browser_for_type(
        selector, fill_raises=fill_err
    )

    monkeypatch.setattr(
        "agent.loop._locate_or_error_msg",
        lambda *_args, **_kwargs: locate_result,
    )

    run_id = "unit-type-timeout"
    writer = _open_click_writer(run_id)

    result_str = _dispatch(
        "type",
        {"intent": "Email textbox", "text": "foo"},
        fake_browser,
        Supervisor(),
        trace_writer=writer,
        run_id=run_id,
        step_id=f"{run_id}:step-1",
    )

    act_events = [e for e in writer.iter_events(run_id) if isinstance(e, ActEvent)]
    assert len(act_events) == 1
    assert act_events[0].outcome == "timeout", (
        f"expected outcome=timeout, got {act_events[0].outcome!r}"
    )
    assert act_events[0].tool == "type"
    assert act_events[0].args["intent"] == "Email textbox"
    assert result_str.startswith("Error: type timeout"), (
        f"expected tool result to start with 'Error: type timeout', got {result_str!r}"
    )
    assert stub_locator.fill_calls == [{"text": "foo", "timeout": 5000}], (
        f"expected one fill call with timeout=5000, got {stub_locator.fill_calls!r}"
    )
    writer.close()


def test_loop_type_playwright_error_yields_outcome_error(monkeypatch):
    import playwright.sync_api as pw_api

    from agent.loop import _dispatch
    from agent.supervisor import Supervisor

    selector = "input#email"
    fill_err = pw_api.Error("element is not an HTMLInputElement")
    fake_browser, locate_result, _stub_locator = _make_fake_browser_for_type(
        selector, fill_raises=fill_err
    )

    monkeypatch.setattr(
        "agent.loop._locate_or_error_msg",
        lambda *_args, **_kwargs: locate_result,
    )

    run_id = "unit-type-error"
    writer = _open_click_writer(run_id)

    result_str = _dispatch(
        "type",
        {"intent": "Email textbox", "text": "foo"},
        fake_browser,
        Supervisor(),
        trace_writer=writer,
        run_id=run_id,
        step_id=f"{run_id}:step-1",
    )

    act_events = [e for e in writer.iter_events(run_id) if isinstance(e, ActEvent)]
    assert len(act_events) == 1
    assert act_events[0].outcome == "error", (
        f"expected outcome=error, got {act_events[0].outcome!r}"
    )
    assert act_events[0].tool == "type"
    assert act_events[0].args["intent"] == "Email textbox"
    assert result_str.startswith("Error: type error"), (
        f"expected tool result to start with 'Error: type error', got {result_str!r}"
    )
    writer.close()


# ---------------------------------------------------------------------------
# Type tool: validation guard — missing/empty intent or text → error, no ActEvent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "args,expected_field",
    [
        ({"text": "foo"}, "intent"),
        ({"intent": "", "text": "foo"}, "intent"),
        ({"intent": "Email textbox"}, "text"),
        ({"intent": "Email textbox", "text": ""}, "text"),
    ],
    ids=["missing-intent", "empty-intent", "missing-text", "empty-text"],
)
def test_loop_type_validation_guard_returns_error_without_locating(args, expected_field):
    import types

    from agent.loop import _dispatch
    from agent.supervisor import Supervisor

    fake_browser = types.SimpleNamespace(_page=None)
    run_id = f"unit-type-guard-{expected_field}-{len(args)}"
    writer = _open_click_writer(run_id)

    result_str = _dispatch(
        "type",
        args,
        fake_browser,
        Supervisor(),
        trace_writer=writer,
        run_id=run_id,
        step_id=f"{run_id}:step-1",
    )

    act_events = [e for e in writer.iter_events(run_id) if isinstance(e, ActEvent)]
    assert result_str.startswith("Error: type requires"), (
        f"expected error string, got {result_str!r}"
    )
    assert expected_field in result_str
    assert len(act_events) == 0, f"locate must not run when {expected_field} guard fires"
    writer.close()


# ---------------------------------------------------------------------------
# Type tool: success path → _dispatch returns spec-mandated "Typed into" string
# ---------------------------------------------------------------------------


def test_loop_type_dispatch_ok_returns_typed_into_string(monkeypatch):
    from agent.loop import _dispatch
    from agent.supervisor import Supervisor

    selector = "input#email"
    fake_browser, locate_result, _stub_locator = _make_fake_browser_for_type(selector)

    monkeypatch.setattr(
        "agent.loop._locate_or_error_msg",
        lambda *_a, **_kw: locate_result,
    )

    run_id = "unit-type-ok"
    writer = _open_click_writer(run_id)

    result_str = _dispatch(
        "type",
        {"intent": "Email textbox", "text": "hello"},
        fake_browser,
        Supervisor(),
        trace_writer=writer,
        run_id=run_id,
        step_id=f"{run_id}:step-1",
    )

    act_events = [e for e in writer.iter_events(run_id) if isinstance(e, ActEvent)]
    assert result_str == "Typed into 'Email textbox' (ok)", (
        f"expected spec-mandated success string, got {result_str!r}"
    )
    assert act_events[0].outcome == "ok"
    assert act_events[0].tool == "type"
    writer.close()


# ---------------------------------------------------------------------------
# Compaction tests (fix-qwen-http-400)
# ---------------------------------------------------------------------------

_LARGE_AX_TREE = "x" * 4096

_LARGE_OBSERVATION = {
    "url": "https://example.com",
    "title": "Example",
    "ax_tree_digest": _LARGE_AX_TREE,
    "ax_fingerprint": "abc123",
    "last_actions": [],
}

_URLS = [
    "https://example.com/1",
    "https://example.com/2",
    "https://example.com/3",
]


def _make_varying_obs_fn() -> object:
    """Returns a side_effect callable that produces LARGE_OBSERVATION with a per-call fingerprint.

    Using a per-call fingerprint prevents the no-progress buffer from filling
    while still exercising message compaction over many steps.
    """
    _count: list[int] = [0]

    def _obs(browser, last_actions):
        fp = format(_count[0], "064x")
        _count[0] += 1
        return {**_LARGE_OBSERVATION, "ax_fingerprint": fp}

    return _obs


class _StubBrowserForCompaction:
    def __init__(self):
        self._page = None
        self._cdp_sessions: dict = {}

    def goto(self, url: str) -> None:
        pass


class _RecordingLLMClient:
    def __init__(self):
        self.all_messages: list[list[dict]] = []
        self._step = 0

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        if tools is None:
            return ChatResponse(
                content='{"steps": ["do the task"], "expected_end_state": "done"}',
                tool_calls=[],
                finish_reason="stop",
                model="fake",
                usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
                raw={},
                usd=0.0,
            )
        self.all_messages.append(list(messages))
        url = _URLS[self._step % len(_URLS)]
        self._step += 1
        return ChatResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id=f"tc-{self._step}",
                    name="goto",
                    arguments=json.dumps({"url": url}),
                )
            ],
            finish_reason="tool_calls",
            model="fake",
            usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            raw={},
        )


def test_loop_compacts_message_history_under_token_budget():
    stub_llm = _RecordingLLMClient()
    stub_browser = _StubBrowserForCompaction()
    with patch("agent.loop.observe.build_observation", side_effect=_make_varying_obs_fn()):
        result = loop("dummy task", browser=stub_browser, llm_client=stub_llm, max_steps=25)

    assert result.status == "timeout"
    last_messages = stub_llm.all_messages[-1]
    total_chars = sum(len(json.dumps(m)) for m in last_messages)
    assert total_chars < 80_000
    for m in last_messages:
        content = m.get("content", "") or ""
        assert "<elided>" not in content
        assert "<read tool result elided>" not in content
    assert last_messages[0]["role"] == "system"


def test_compact_messages_no_op_when_under_budget():
    from agent.loop import _compact_messages

    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "Current state: small"},
        {"role": "assistant", "content": "ok"},
    ]
    snapshot = [dict(m) for m in messages]
    out = _compact_messages(messages, budget_chars=10_000)
    assert out is messages
    assert messages == snapshot


def test_loop_preserves_most_recent_observation_after_compaction():
    stub_llm = _RecordingLLMClient()
    stub_browser = _StubBrowserForCompaction()
    with patch("agent.loop.observe.build_observation", side_effect=_make_varying_obs_fn()):
        result = loop("dummy task", browser=stub_browser, llm_client=stub_llm, max_steps=25)

    assert result.status == "timeout"
    last_messages = stub_llm.all_messages[-1]
    state_msgs = [
        m
        for m in last_messages
        if m.get("role") == "user" and "Current state: " in m.get("content", "")
    ]
    assert len(state_msgs) >= 1
    last_user_state_msg = state_msgs[-1]

    assert "ax_tree_digest" in last_user_state_msg["content"]
    assert _LARGE_AX_TREE[:64] in last_user_state_msg["content"]

    assert len(state_msgs) >= 2, (
        "compaction is expected to keep multiple state msgs in the final call "
        "under this stub setup; 25 steps should produce a multi-state tail"
    )
    assert len(stub_llm.all_messages) >= 2
    prev_call = stub_llm.all_messages[-2]
    prev_state_msgs = [
        m
        for m in prev_call
        if m.get("role") == "user" and "Current state: " in m.get("content", "")
    ]
    assert prev_state_msgs, "prior chat call must have at least one state msg"
    assert any(m is state_msgs[-2] for m in prev_state_msgs), (
        "state msg from the prior step should be the same object across "
        "chat calls (compaction must not copy/mutate kept messages)"
    )

    assert last_messages[0]["role"] == "system"
    assert last_messages[0]["content"] == _build_system_prompt("dummy task")


def test_compact_messages_kept_tail_byte_identical():
    from agent.loop import _compact_messages

    messages: list[dict] = [{"role": "system", "content": "S" * 200}]
    for i in range(40):
        messages.append({"role": "user", "content": f"Current state: payload-{i}-" + ("x" * 500)})
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"tc-{i}",
                        "type": "function",
                        "function": {"name": "goto", "arguments": "{}"},
                    }
                ],
            }
        )
        messages.append({"role": "tool", "tool_call_id": f"tc-{i}", "content": "T" * 500})

    input_ids = {id(m) for m in messages}
    snapshot = [dict(m) for m in messages]

    out = _compact_messages(messages, budget_chars=10_000)
    total = sum(len(json.dumps(m)) for m in out)
    assert total <= 10_000 or len(out) <= 2

    for m in out:
        assert id(m) in input_ids
        content = m.get("content", "") or ""
        assert "<elided>" not in content
        assert "<read tool result elided>" not in content

    assert messages == snapshot


def test_compact_messages_prefix_stability_across_consecutive_calls():
    from agent.loop import _compact_messages

    def _turn(i: int) -> list[dict]:
        return [
            {"role": "user", "content": f"Current state: payload-{i}-" + ("x" * 500)},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"tc-{i}",
                        "type": "function",
                        "function": {"name": "goto", "arguments": "{}"},
                    }
                ],
            },
            {"role": "tool", "tool_call_id": f"tc-{i}", "content": "T" * 500},
        ]

    L1: list[dict] = [{"role": "system", "content": "S" * 200}]
    for i in range(30):
        L1.extend(_turn(i))

    R1 = list(_compact_messages([dict(m) for m in L1], budget_chars=10_000))

    L2 = [dict(m) for m in L1]
    L2.extend(_turn(30))

    R2 = list(_compact_messages(L2, budget_chars=10_000))

    def _is_new(m: dict) -> bool:
        if m.get("role") == "user" and "payload-30" in (m.get("content") or ""):
            return True
        if m.get("role") == "tool" and m.get("tool_call_id") == "tc-30":
            return True
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                if tc.get("id") == "tc-30":
                    return True
        return False

    overlap_R2 = [m for m in R2 if not _is_new(m)]
    if overlap_R2 and overlap_R2[0].get("role") == "system":
        overlap_R2 = overlap_R2[1:]
    R1_tail = R1[1:]

    assert len(overlap_R2) > 0
    assert len(overlap_R2) <= len(R1_tail)
    k = len(R1_tail) - len(overlap_R2)
    assert R1_tail[k:] == overlap_R2


def test_compact_messages_preserves_system_and_last_state():
    from agent.loop import _compact_messages

    sys_msg = {"role": "system", "content": "SYS"}
    last_state = {"role": "user", "content": "Current state: NEWEST"}
    messages: list[dict] = [sys_msg]
    for i in range(50):
        messages.append({"role": "user", "content": f"Current state: old-{i}-" + ("x" * 800)})
        messages.append({"role": "tool", "tool_call_id": f"tc-{i}", "content": "T" * 800})
    messages.append(last_state)

    out = _compact_messages(messages, budget_chars=5_000)
    assert out[0] is sys_msg
    assert any(m is last_state for m in out)


def test_compact_messages_minimum_keep_set_when_over_budget():
    from agent.loop import _compact_messages

    sys_msg = {"role": "system", "content": "S" * 5_000}
    last_state = {"role": "user", "content": "Current state: " + ("X" * 5_000)}
    messages: list[dict] = [sys_msg]
    for i in range(20):
        messages.append({"role": "user", "content": f"Current state: old-{i}-" + ("x" * 500)})
        messages.append({"role": "tool", "tool_call_id": f"tc-{i}", "content": "T" * 500})
    messages.append(last_state)

    out = _compact_messages(messages, budget_chars=1_000)
    assert out == [sys_msg, last_state]
    assert out[0] is sys_msg
    assert out[1] is last_state


def test_compact_messages_advances_past_orphan_tool_after_mid_turn_split():
    from agent.loop import _compact_messages

    sys_msg = {"role": "system", "content": "S" * 100}
    last_state = {"role": "user", "content": "Current state: NEWEST"}

    messages: list[dict] = [sys_msg]
    messages.append({"role": "user", "content": "Current state: turn-0-" + ("x" * 200)})
    messages.append(
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "tc-0",
                    "type": "function",
                    "function": {"name": "goto", "arguments": "{}"},
                }
            ],
        }
    )
    messages.append({"role": "tool", "tool_call_id": "tc-0", "content": "T" * 4_000})
    messages.append(last_state)

    out = _compact_messages(messages, budget_chars=300)

    assert out[0] is sys_msg
    assert out[-1] is last_state

    kept_assistant_tc_ids: set[str] = set()
    for m in out:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls") or []:
                kept_assistant_tc_ids.add(tc["id"])
    for m in out:
        if m.get("role") == "tool":
            assert m["tool_call_id"] in kept_assistant_tc_ids, (
                "kept tool message has no kept assistant parent — orphan tool"
            )


def test_compact_messages_no_op_when_no_state_message_present():
    from agent.loop import _compact_messages

    messages: list[dict] = [{"role": "system", "content": "S" * 200}]
    for i in range(20):
        messages.append({"role": "user", "content": f"plain user msg {i} " + ("x" * 500)})
        messages.append({"role": "assistant", "content": f"reply {i} " + ("y" * 500)})

    snapshot = [dict(m) for m in messages]
    out = _compact_messages(messages, budget_chars=1_000)
    assert out is messages
    assert messages == snapshot


def test_compact_messages_drops_at_turn_boundary():
    from agent.loop import _compact_messages

    sys_msg = {"role": "system", "content": "SYS"}
    messages: list[dict] = [sys_msg]
    for i in range(15):
        messages.append({"role": "user", "content": f"Current state: turn-{i}-" + ("x" * 400)})
        messages.append(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"tc-{i}",
                        "type": "function",
                        "function": {"name": "goto", "arguments": "{}"},
                    }
                ],
            }
        )
        messages.append({"role": "tool", "tool_call_id": f"tc-{i}", "content": "T" * 400})

    out = _compact_messages(messages, budget_chars=8_000)

    assert out[0] is sys_msg
    if len(out) > 1:
        assert out[1].get("role") == "user"
        assert "Current state: " in out[1].get("content", "")

    kept_assistant_tc_ids: set[str] = set()
    for m in out:
        if m.get("role") == "assistant":
            for tc in m.get("tool_calls", []) or []:
                kept_assistant_tc_ids.add(tc["id"])
    for m in out:
        if m.get("role") == "tool":
            assert m["tool_call_id"] in kept_assistant_tc_ids

    kept_tool_call_ids = {m["tool_call_id"] for m in out if m.get("role") == "tool"}
    for tc_id in kept_assistant_tc_ids:
        assert tc_id in kept_tool_call_ids, (
            f"assistant tool_call id {tc_id!r} kept without its tool result — "
            "OpenAI-compatible APIs reject this"
        )


# ---------------------------------------------------------------------------
# Stuck-repeat detection tests
# ---------------------------------------------------------------------------


class _AlwaysGotoClient:
    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        if tools is None:
            return ChatResponse(
                content='{"steps": ["do the task"], "expected_end_state": "done"}',
                tool_calls=[],
                finish_reason="stop",
                model="fake",
                usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
                raw={},
                usd=0.0,
            )
        return ChatResponse(
            content=None,
            tool_calls=[
                ToolCall(id="tc-stuck", name="goto", arguments=json.dumps({"url": "about:blank"}))
            ],
            finish_reason="tool_calls",
            model="fake",
            usage=_DUMMY_USAGE,
            raw={},
        )


def test_loop_stuck_repeat_exits_early():
    stub_browser = _StubBrowserForCompaction()
    stub_llm = _AlwaysGotoClient()
    with patch("agent.loop.observe.build_observation", return_value=_LARGE_OBSERVATION):
        result = loop("task", browser=stub_browser, llm_client=stub_llm, max_steps=20)
    assert result.status == "failed"
    assert result.reason == "stuck_repeat"
    assert result.steps == 3


class _AlternatingGotoClient:
    def __init__(self):
        self._urls = ["http://a", "http://b", "http://a"]
        self._step = 0

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        if tools is None:
            return ChatResponse(
                content='{"steps": ["do the task"], "expected_end_state": "done"}',
                tool_calls=[],
                finish_reason="stop",
                model="fake",
                usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
                raw={},
                usd=0.0,
            )
        if self._step < len(self._urls):
            url = self._urls[self._step]
            self._step += 1
            return ChatResponse(
                content=None,
                tool_calls=[
                    ToolCall(id=f"tc-{self._step}", name="goto", arguments=json.dumps({"url": url}))
                ],
                finish_reason="tool_calls",
                model="fake",
                usage=_DUMMY_USAGE,
                raw={},
            )
        return _response_no_tool_call()


def test_loop_stuck_repeat_no_false_positive_on_alternation():
    stub_browser = _StubBrowserForCompaction()
    stub_llm = _AlternatingGotoClient()
    with patch("agent.loop.observe.build_observation", return_value=_LARGE_OBSERVATION):
        result = loop("task", browser=stub_browser, llm_client=stub_llm, max_steps=20)
    assert result.reason != "stuck_repeat"
    assert result.status == "failed"
    assert result.reason == "no_tool_call_repeat"
    assert result.steps == 6


# ---------------------------------------------------------------------------
# Regression: stuck-repeat must not pre-empt the supervisor halt/replan path.
# 4 consecutive read(intent=X) calls exhaust the supervisor's max_attempts=3
# (attempt 4 > 3 triggers halt).  Stuck-detection must not fire first.
# ---------------------------------------------------------------------------


class _ZeroCountLocator:
    def count(self) -> int:
        return 0

    def filter(self, **_kwargs) -> _ZeroCountLocator:
        return self


class _AlwaysMissPage:
    url = "about:blank"

    def get_by_role(self, *_args, **_kwargs) -> _ZeroCountLocator:
        return _ZeroCountLocator()

    def get_by_placeholder(self, *_args, **_kwargs) -> _ZeroCountLocator:
        return _ZeroCountLocator()

    def locator(self, *_args, **_kwargs) -> _ZeroCountLocator:
        return _ZeroCountLocator()


class _StubBrowserWithMissPage:
    def __init__(self):
        self._page = _AlwaysMissPage()
        self._cdp_sessions: dict = {}

    def goto(self, url: str) -> None:
        pass


def test_loop_stuck_repeat_does_not_preempt_supervisor_halt():
    read_tc = [
        _response_with_tool_call(
            _tool_call("read", {"intent": "Submit button"}, call_id=f"tc-r{i}")
        )
        for i in range(1, 5)
    ]
    done_tc = _response_with_tool_call(
        _tool_call(
            "done",
            {"result": {"note": "ok"}, "evidence": {"url": "about:blank", "text_snippet": "x"}},
            call_id="tc-done",
        )
    )
    fake_llm = _FakeLLMClient(read_tc + [done_tc])
    stub_browser = _StubBrowserWithMissPage()
    with patch("agent.loop.observe.build_observation", return_value="state: ok"):
        result = loop("task", browser=stub_browser, llm_client=fake_llm, max_steps=10)
    assert result.reason != "stuck_repeat"
    assert result.steps >= 4


# ---------------------------------------------------------------------------
# No-tool-call-repeat detection tests
# ---------------------------------------------------------------------------


class _AlwaysNoToolCallClient:
    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        if tools is None:
            return ChatResponse(
                content='{"steps": ["do the task"], "expected_end_state": "done"}',
                tool_calls=[],
                finish_reason="stop",
                model="fake",
                usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
                raw={},
                usd=0.0,
            )
        return ChatResponse(
            content="thinking...",
            tool_calls=[],
            finish_reason="stop",
            model="fake",
            usage=_DUMMY_USAGE,
            raw={},
        )


def test_no_tool_call_repeat_exits_at_k():
    stub_browser = _StubBrowserForCompaction()
    stub_llm = _AlwaysNoToolCallClient()
    with patch("agent.loop.observe.build_observation", return_value="state: ok"):
        result = loop("task", browser=stub_browser, llm_client=stub_llm, max_steps=20)
    assert result.status == "failed"
    assert result.reason == "no_tool_call_repeat"
    assert result.steps == 3


class _NoToolCallThenGotoClient:
    def __init__(self):
        self._step = 0

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        if tools is None:
            return ChatResponse(
                content='{"steps": ["do the task"], "expected_end_state": "done"}',
                tool_calls=[],
                finish_reason="stop",
                model="fake",
                usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
                raw={},
                usd=0.0,
            )
        self._step += 1
        if self._step % 3 == 0:
            return ChatResponse(
                content=None,
                tool_calls=[
                    ToolCall(
                        id=f"tc-goto-{self._step}",
                        name="goto",
                        arguments=json.dumps({"url": f"http://example.com/{self._step}"}),
                    )
                ],
                finish_reason="tool_calls",
                model="fake",
                usage=_DUMMY_USAGE,
                raw={},
            )
        return ChatResponse(
            content="thinking...",
            tool_calls=[],
            finish_reason="stop",
            model="fake",
            usage=_DUMMY_USAGE,
            raw={},
        )


def test_no_tool_call_repeat_resets_on_tool_call():
    stub_browser = _StubBrowserForCompaction()
    stub_llm = _NoToolCallThenGotoClient()
    with patch("agent.loop.observe.build_observation", return_value="state: ok"):
        result = loop("task", browser=stub_browser, llm_client=stub_llm, max_steps=20)
    assert result.status == "timeout"
    assert result.steps == 20
    assert result.reason is None


# ---------------------------------------------------------------------------
# expect threading into system prompt
# ---------------------------------------------------------------------------


def test_loop_threads_expect_to_system_prompt():
    done_call = _tool_call(
        "done",
        {
            "result": {"answer": "X"},
            "evidence": {"url": "http://x", "text_snippet": "X"},
        },
        call_id="tc-done",
    )
    stub_llm = _CapturingLLMClient([_response_with_tool_call(done_call)])
    with patch("agent.loop.observe.build_observation", return_value="state: ok"):
        loop(
            "find the price",
            _StubBrowserForCompaction(),
            stub_llm,
            expect={"schema": {"answer": "str"}, "validators": ["answer.nonempty"]},
        )
    assert stub_llm.captured_messages is not None
    system_msg = stub_llm.captured_messages[0]
    assert system_msg["role"] == "system"
    assert "MUST" in system_msg["content"]
    assert "answer" in system_msg["content"]


# ---------------------------------------------------------------------------
# budget_seconds wall-clock cutoff (ticket #89)
# ---------------------------------------------------------------------------


class _SleepingLLMClient:
    """Sleeps `sleep_s` seconds on every non-planner chat call and returns a
    non-terminal `goto` tool call so the loop runs until something else cuts it
    off (max_steps or budget_seconds).
    """

    def __init__(self, sleep_s: float):
        self._sleep_s = sleep_s
        self._step = 0

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        if tools is None:
            return _plan_stub_response()
        import time as _t

        _t.sleep(self._sleep_s)
        self._step += 1
        return ChatResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id=f"tc-{self._step}",
                    name="goto",
                    arguments=json.dumps({"url": f"http://example.invalid/{self._step}"}),
                )
            ],
            finish_reason="tool_calls",
            model="fake",
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            raw={},
            usd=0.001,
        )


def test_loop_terminates_on_budget_seconds():
    stub_llm = _SleepingLLMClient(sleep_s=1.0)
    stub_browser = _StubBrowserForCompaction()
    with patch("agent.loop.observe.build_observation", return_value="state: ok"):
        result = loop(
            "dummy task",
            browser=stub_browser,
            llm_client=stub_llm,
            max_steps=100,
            budget_seconds=2.5,
        )
    assert result.status == "timeout"
    assert result.reason == "seconds_budget"
    assert 2 <= result.steps <= 4, f"expected 2..4 steps, got {result.steps}"
    assert len(result.latency_ms_per_step) == result.steps
    assert result.latency_ms_total == sum(result.latency_ms_per_step)
    assert result.prompt_tokens >= 10 * result.steps
    assert result.completion_tokens == 5 * result.steps
    assert len(result.step_breakdown) == result.steps


def test_loop_no_budget_seconds_default_unchanged():
    """Without budget_seconds, the loop completes on the natural happy path."""
    done_call = _tool_call(
        "done",
        {
            "result": {"answer": "X"},
            "evidence": {"url": "http://x", "text_snippet": "X"},
        },
        call_id="tc-done",
    )
    fake_llm = _FakeLLMClient([_response_with_tool_call(done_call)])
    with patch("agent.loop.observe.build_observation", return_value="state: ok"):
        result = loop("task", _StubBrowserForCompaction(), fake_llm, max_steps=5)
    assert result.status == "succeeded"
    assert result.reason is None


def test_run_case_threads_seconds_budget(monkeypatch):
    """`_run_case` SHALL pass `budget_seconds=case['budget']['seconds']` to loop()."""
    from scripts import eval as eval_mod

    captured: dict = {}

    def _fake_loop(*args, **kwargs):
        captured.update(kwargs)
        return RunResult(
            status="succeeded",
            result={"answer": "ok"},
            evidence={"url": "http://x", "text_snippet": "ok"},
            verifier=None,
            steps=1,
            prompt_tokens=0,
            completion_tokens=0,
            usd=0.0,
            latency_ms_total=0,
            latency_ms_per_step=[0],
            step_breakdown=[
                {
                    "step": 1,
                    "latency_ms": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "usd": 0.0,
                    "tool_calls": ["done"],
                }
            ],
            reason=None,
        )

    monkeypatch.setattr(eval_mod, "loop", _fake_loop)

    class _NoopBrowser:
        def goto(self, url):
            pass

    class _NoopLLM:
        def chat(self, *a, **kw):
            raise AssertionError("loop is mocked; LLM should not be called")

    case = {
        "id": "demo-1",
        "domain": "demo",
        "category": "demo",
        "task": "demo task",
        "expect": {"schema": {"answer": "str"}, "validators": ["answer.nonempty"]},
        "budget": {"steps": 5, "usd": 0.01, "seconds": 42},
    }
    eval_mod._run_case(case, llm_client=_NoopLLM(), browser=_NoopBrowser())

    assert captured.get("budget_seconds") == 42


def test_loop_budget_seconds_signature_accepts_kwarg():
    import inspect

    from agent import loop as loop_mod

    sig = inspect.signature(loop_mod.loop)
    assert "budget_seconds" in sig.parameters
    p = sig.parameters["budget_seconds"]
    assert p.default is None
    assert p.kind == inspect.Parameter.KEYWORD_ONLY
