from __future__ import annotations

import json
from unittest.mock import patch

from agent.llm import ChatResponse, ToolCall, Usage
from agent.loop import loop

_LARGE_AX_TREE = "x" * 4096

_LARGE_OBSERVATION = {
    "url": "https://example.com",
    "title": "Example",
    "ax_tree_digest": _LARGE_AX_TREE,
    "ax_fingerprint": "abc123",
    "last_actions": [],
}

_URLS = [
    "https://example.com/a",
    "https://example.com/b",
    "https://example.com/c",
]


def _is_planner_call(messages: list[dict]) -> bool:
    if not messages:
        return False
    first = messages[0]
    content = first.get("content", "") if isinstance(first, dict) else ""
    return isinstance(content, str) and content.startswith("You are a planning assistant")


class _StubBrowser:
    def __init__(self):
        self._page = None
        self._cdp_sessions: dict = {}

    def goto(self, url: str) -> None:
        pass


class _RecordingStubLLM:
    def __init__(self):
        self.all_messages: list[list[dict]] = []
        self._step = 0

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        if tools is None or _is_planner_call(messages):
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


def test_no_llm_error_after_25_steps():
    stub_llm = _RecordingStubLLM()
    stub_browser = _StubBrowser()

    _n: list[int] = [0]

    def _varying_obs(browser, last_actions):
        obs = {**_LARGE_OBSERVATION, "ax_fingerprint": format(_n[0], "064x")}
        _n[0] += 1
        return obs

    with patch("agent.loop.observe.build_observation", side_effect=_varying_obs):
        result = loop("dummy task", browser=stub_browser, llm_client=stub_llm, max_steps=25)

    assert result.status == "timeout"
    last_messages = stub_llm.all_messages[-1]
    total_chars = sum(len(json.dumps(m)) for m in last_messages)
    assert total_chars < 80_000
