from __future__ import annotations

import json
import time
from unittest.mock import MagicMock, patch

from agent.llm import ChatResponse, ToolCall, Usage
from agent.loop import loop

_DUMMY_USAGE = Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2)

_PLAN_STUB = (
    '{"steps": ["start the task", "complete the task"], "expected_end_state": "task complete"}'
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


def _judge_stub_response() -> ChatResponse:
    return ChatResponse(
        content='{"verdict": "supported", "reason": "stub"}',
        tool_calls=[],
        finish_reason="stop",
        model="fake",
        usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        raw={},
        usd=0.0,
    )


def _is_judge_call(messages: list[dict]) -> bool:
    if not messages:
        return False
    first = messages[0]
    content = first.get("content", "") if isinstance(first, dict) else ""
    return isinstance(content, str) and "[VERIFY DONE]" in content


def _is_planner_call(messages: list[dict]) -> bool:
    if not messages:
        return False
    first = messages[0]
    content = first.get("content", "") if isinstance(first, dict) else ""
    return isinstance(content, str) and content.startswith("You are a planning assistant")


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
        content="thinking",
        tool_calls=[],
        finish_reason="stop",
        model="fake",
        usage=_DUMMY_USAGE,
        raw={},
    )


def _fake_observation() -> dict:
    return {
        "url": "http://fake",
        "title": "Fake",
        "ax_tree_digest": "",
        "ax_fingerprint": "0" * 64,
        "last_actions": [],
    }


class _SleepingLLMClient:
    """LLM client that sleeps 0.4 s per chat call before returning canned responses."""

    def __init__(self, responses: list[ChatResponse]):
        self._responses = list(responses)
        self._index = 0

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        if _is_judge_call(messages):
            return _judge_stub_response()
        if tools is None or _is_planner_call(messages):
            return _plan_stub_response()
        time.sleep(0.4)
        if self._index < len(self._responses):
            resp = self._responses[self._index]
            self._index += 1
            return resp
        return _response_no_tool_call()


class _SimpleLLMClient:
    """LLM client with no sleep, returns canned responses."""

    def __init__(self, responses: list[ChatResponse]):
        self._responses = list(responses)
        self._index = 0

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        if _is_judge_call(messages):
            return _judge_stub_response()
        if tools is None or _is_planner_call(messages):
            return _plan_stub_response()
        if self._index < len(self._responses):
            resp = self._responses[self._index]
            self._index += 1
            return resp
        return _response_no_tool_call()


def _make_stub_browser() -> MagicMock:
    browser = MagicMock()
    browser._page = None
    return browser


def test_phase_ranges_match_stub_sleep_durations():
    """Stub LLM sleeps 0.4 s; stub observation sleeps 0.1 s; assert phase ranges."""
    done_tc = _tool_call(
        "done",
        {
            "result": {"answer": "ok"},
            "evidence": {"url": "http://fake", "text_snippet": "ok"},
        },
        call_id="tc-done",
    )
    llm = _SleepingLLMClient([_response_with_tool_call(done_tc)])
    browser = _make_stub_browser()

    def _slow_build_observation(br, last_actions):
        time.sleep(0.1)
        return _fake_observation()

    with patch("agent.loop.observe.build_observation", side_effect=_slow_build_observation):
        result = loop("fake task", browser, llm)

    assert result.status == "succeeded"
    assert len(result.step_breakdown) == 1
    bd = result.step_breakdown[0]
    lbm = bd["latency_breakdown_ms"]
    assert 350 <= lbm["llm_ms"] <= 600, f"llm_ms={lbm['llm_ms']} not in [350, 600]"
    assert 80 <= lbm["observation_ms"] <= 200, (
        f"observation_ms={lbm['observation_ms']} not in [80, 200]"
    )


def test_sum_invariant_holds_across_5_step_run():
    """abs((obs + llm + dispatch) - latency_ms) <= 5 for every step in a 5-step run."""
    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": f"http://fake/{i}"}, call_id=f"tc-{i}"))
        for i in range(4)
    ]
    responses.append(
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {"answer": "ok"},
                    "evidence": {"url": "http://fake", "text_snippet": "ok"},
                },
                call_id="tc-done",
            )
        )
    )
    llm = _SimpleLLMClient(responses)
    browser = _make_stub_browser()

    _call_n: list[int] = [0]

    def _varying_obs(br, last_actions):
        obs = {**_fake_observation(), "ax_fingerprint": format(_call_n[0], "064x")}
        _call_n[0] += 1
        return obs

    with (
        patch("agent.loop.observe.build_observation", side_effect=_varying_obs),
        patch("agent.loop._dispatch", return_value="ok"),
    ):
        result = loop("fake task", browser, llm)

    assert len(result.step_breakdown) == 5
    for s in result.step_breakdown:
        lbm = s["latency_breakdown_ms"]
        total = lbm["observation_ms"] + lbm["llm_ms"] + lbm["dispatch_ms"]
        diff = abs(total - s["latency_ms"])
        assert diff <= 5, (
            f"step {s['step']}: obs+llm+dispatch={total} "
            f"vs latency_ms={s['latency_ms']}, diff={diff}"
        )


def test_latency_breakdown_present_on_all_entries_including_no_tool_call():
    """Every step_breakdown entry has latency_breakdown_ms with all three integer keys."""
    done_tc = _tool_call(
        "done",
        {
            "result": {"answer": "ok"},
            "evidence": {"url": "http://fake", "text_snippet": "ok"},
        },
        call_id="tc-3",
    )
    llm = _SimpleLLMClient(
        [_response_no_tool_call(), _response_no_tool_call(), _response_with_tool_call(done_tc)]
    )
    browser = _make_stub_browser()

    with patch("agent.loop.observe.build_observation", return_value=_fake_observation()):
        result = loop("fake task", browser, llm)

    assert len(result.step_breakdown) == 3
    for entry in result.step_breakdown:
        assert "latency_breakdown_ms" in entry, (
            f"missing latency_breakdown_ms in step {entry['step']}"
        )
        lbm = entry["latency_breakdown_ms"]
        for key in ("observation_ms", "llm_ms", "dispatch_ms"):
            assert key in lbm, f"missing key {key!r} in step {entry['step']}"
            assert lbm[key] is not None, f"None value for {key!r} in step {entry['step']}"
            assert isinstance(lbm[key], int), f"{key!r} is not int in step {entry['step']}"
        total = lbm["observation_ms"] + lbm["llm_ms"] + lbm["dispatch_ms"]
        diff = abs(total - entry["latency_ms"])
        assert diff <= 5, (
            f"step {entry['step']}: obs+llm+dispatch={total} "
            f"vs latency_ms={entry['latency_ms']}, diff={diff}"
        )
