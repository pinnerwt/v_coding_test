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
    assert obs_json["last_action"] is None


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
    assert obs_json["last_action"] is not None
    assert obs_json["last_action"]["tool"] == "goto"


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


def test_supervisor_halt_triggers_replan_event(fixture_server, playwright_chromium):
    fixture_url = f"{fixture_server}/index.html"
    plan_json = '{"steps": ["step 1", "step 2"], "expected_end_state": "done"}'
    replan_json = '{"steps": ["alt step 1", "alt step 2"], "expected_end_state": "alt done"}'

    class _HaltReplanLLM:
        """
        Call sequence (tools=None → planner/replan call, tools=TOOLS → decision call):
        idx=0: plan call → plan_json
        idx=1+: decision calls → keep returning read (triggers halt)
               once replan is triggered (no tools, after first halt):
               → replan_json
               then decision calls → done
        """

        def __init__(self):
            self._call_index = 0
            self._replan_sent = False
            self._done_after_replan = False

        def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
            idx = self._call_index
            self._call_index += 1
            if idx == 0:
                return _fake_text_response(plan_json)
            if tools is None and not self._replan_sent:
                self._replan_sent = True
                return _fake_text_response(replan_json)
            if self._replan_sent and tools is not None and not self._done_after_replan:
                self._done_after_replan = True
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

    llm = _HaltReplanLLM()
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
