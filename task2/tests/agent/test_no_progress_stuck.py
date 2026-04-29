from __future__ import annotations

import json
from unittest.mock import patch

from agent.llm import ChatResponse, ToolCall, Usage
from agent.loop import loop

_DUMMY_USAGE = Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2)

_CONSTANT_FP = "f" * 64

_CONSTANT_OBS = {
    "url": "https://example.com",
    "title": "Example",
    "ax_tree_digest": "some content",
    "ax_fingerprint": _CONSTANT_FP,
    "last_actions": [],
}


def _plan_stub() -> ChatResponse:
    return ChatResponse(
        content='{"steps": ["complete the task"], "expected_end_state": "task complete"}',
        tool_calls=[],
        finish_reason="stop",
        model="fake",
        usage=Usage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        raw={},
        usd=0.0,
    )


class _StubBrowser:
    def __init__(self):
        self._page = None
        self._cdp_sessions: dict = {}

    def goto(self, url: str) -> None:
        pass


class _ReadEachStepClient:
    """Emits read(intent=f'x{i}') each step — different args every step (no stuck_repeat)."""

    def __init__(self):
        self._step = 0

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        if tools is None:
            return _plan_stub()
        self._step += 1
        return ChatResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id=f"tc-{self._step}",
                    name="read",
                    arguments=json.dumps({"intent": f"x{self._step}"}),
                )
            ],
            finish_reason="tool_calls",
            model="fake",
            usage=_DUMMY_USAGE,
            raw={},
        )


class _AlternatingFpBrowser:
    """Returns alternating ax_fingerprint values — alternates every 2 calls (pre+post per step)."""

    def __init__(self):
        self._page = None
        self._cdp_sessions: dict = {}
        self._call_count = 0

    def goto(self, url: str) -> None:
        pass

    def next_obs(self, last_actions: list[dict]) -> dict:
        fp = "a" * 64 if (self._call_count // 2) % 2 == 0 else "b" * 64
        self._call_count += 1
        return {
            "url": "https://example.com",
            "title": "Example",
            "ax_tree_digest": "some content",
            "ax_fingerprint": fp,
            "last_actions": last_actions,
        }


class _ClickOkEachStepClient:
    """Emits click(intent='button') each step."""

    def __init__(self):
        self._step = 0

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        if tools is None:
            return _plan_stub()
        self._step += 1
        return ChatResponse(
            content=None,
            tool_calls=[
                ToolCall(
                    id=f"tc-{self._step}",
                    name="click",
                    arguments=json.dumps({"intent": "button"}),
                )
            ],
            finish_reason="tool_calls",
            model="fake",
            usage=_DUMMY_USAGE,
            raw={},
        )


class _StubLocator:
    """Locator stub that succeeds click calls."""

    @property
    def first(self) -> _StubLocator:
        return self

    def count(self) -> int:
        return 1

    def filter(self, **_kwargs) -> _StubLocator:
        return self

    def evaluate(self, *_args, **_kwargs) -> str:
        return "button"

    def click(self, timeout: int = 5000) -> None:
        pass


class _StubPageWithClick:
    url = "https://example.com"
    title_val = "Example"

    def get_by_role(self, *_args, **_kwargs) -> _StubLocator:
        return _StubLocator()

    def get_by_placeholder(self, *_args, **_kwargs) -> _StubLocator:
        return _StubLocator()

    def locator(self, *_args, **_kwargs) -> _StubLocator:
        return _StubLocator()

    def title(self) -> str:
        return self.title_val

    def wait_for_load_state(self, *_args, **_kwargs) -> None:
        pass


class _StubBrowserWithClick:
    def __init__(self):
        self._page = _StubPageWithClick()
        self._cdp_sessions: dict = {}

    def goto(self, url: str) -> None:
        pass


def test_no_progress_bail_after_4_unchanged_fingerprint_steps_no_successful_action():
    """Constant fingerprint + read-only steps → bail at step 4 with reason=no_progress."""
    stub_browser = _StubBrowser()
    stub_llm = _ReadEachStepClient()
    with patch("agent.loop.observe.build_observation", return_value=_CONSTANT_OBS):
        result = loop("task", browser=stub_browser, llm_client=stub_llm, max_steps=20)
    assert result.status == "failed"
    assert result.reason == "no_progress"
    assert result.steps == 4
    assert len(result.step_breakdown) == 4


def test_no_progress_alternating_fingerprint_does_not_bail():
    """Alternating fingerprints prevent no_progress detection; loop runs to another termination."""
    alt_browser = _AlternatingFpBrowser()
    stub_llm = _ReadEachStepClient()

    def _alternating_obs(browser, last_actions):
        return alt_browser.next_obs(last_actions)

    with patch("agent.loop.observe.build_observation", side_effect=_alternating_obs):
        result = loop("task", browser=alt_browser, llm_client=stub_llm, max_steps=6)
    assert not (result.status == "failed" and result.reason == "no_progress")


def test_no_progress_constant_fingerprint_with_successful_click_does_not_bail():
    """Constant fingerprint but click succeeds → any_action_succeeded=True → no bail."""
    stub_browser = _StubBrowserWithClick()
    stub_llm = _ClickOkEachStepClient()
    with patch("agent.loop.observe.build_observation", return_value=_CONSTANT_OBS):
        result = loop("task", browser=stub_browser, llm_client=stub_llm, max_steps=20)
    assert result.reason != "no_progress"
