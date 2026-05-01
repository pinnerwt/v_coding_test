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


def _is_planner_call(messages: list[dict]) -> bool:
    if not messages:
        return False
    first = messages[0]
    content = first.get("content", "") if isinstance(first, dict) else ""
    return isinstance(content, str) and content.startswith("You are a planning assistant")


def _plan_stub() -> ChatResponse:
    return ChatResponse(
        content=(
            '{"steps": ["start the task", "complete the task"],'
            ' "expected_end_state": "task complete"}'
        ),
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
        if tools is None or _is_planner_call(messages):
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
        if tools is None or _is_planner_call(messages):
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


def test_no_progress_bail_after_two_consecutive_unchanged_fingerprint_windows():
    """Constant fingerprint + read-only steps → first 4-step window triggers a
    'force done' warning, second 4-step window fails with reason=no_progress."""
    stub_browser = _StubBrowser()
    stub_llm = _ReadEachStepClient()
    with patch("agent.loop.observe.build_observation", return_value=_CONSTANT_OBS):
        result = loop("task", browser=stub_browser, llm_client=stub_llm, max_steps=20)
    assert result.status == "failed"
    assert result.reason == "no_progress"
    assert result.steps == 8
    assert len(result.step_breakdown) == 8
    for entry in result.step_breakdown:
        bd = entry["latency_breakdown_ms"]
        assert isinstance(bd["observation_ms"], int)
        assert isinstance(bd["llm_ms"], int)
        assert isinstance(bd["dispatch_ms"], int)


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


class _GotoThenBodyReadsClient:
    """Step 1: goto. Steps 2+: read without intent (returns body text)."""

    def __init__(self):
        self._step = 0

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        if tools is None or _is_planner_call(messages):
            return _plan_stub()
        self._step += 1
        if self._step == 1:
            tc = ToolCall(
                id="tc-goto",
                name="goto",
                arguments=json.dumps({"url": "https://example.com"}),
            )
        else:
            tc = ToolCall(
                id=f"tc-{self._step}",
                name="read",
                arguments=json.dumps({}),
            )
        return ChatResponse(
            content=None,
            tool_calls=[tc],
            finish_reason="tool_calls",
            model="fake",
            usage=_DUMMY_USAGE,
            raw={},
        )


class _BodyTextPage:
    url = "https://example.com"

    def title(self) -> str:
        return "Example"

    def evaluate(self, *_args, **_kwargs) -> str:
        return "Example Domain\n\nbody text"


class _StubBrowserWithBody:
    def __init__(self):
        self._page = _BodyTextPage()
        self._cdp_sessions: dict = {}

    def goto(self, url: str) -> None:
        pass


def test_goto_followed_by_body_reads_does_not_bail_no_progress():
    """Regression for live smoke (2026-04-29): goto step 1 + body-read steps 2-4
    + body-read step 5 → fingerprint constant, but read returned body text (success).
    Detector must not bail with no_progress before LLM has a chance to call done.
    """
    stub_browser = _StubBrowserWithBody()
    stub_llm = _GotoThenBodyReadsClient()
    with patch("agent.loop.observe.build_observation", return_value=_CONSTANT_OBS):
        result = loop("task", browser=stub_browser, llm_client=stub_llm, max_steps=6)
    assert result.reason != "no_progress", (
        f"goto+body-reads incorrectly classified as no_progress; "
        f"status={result.status} steps={result.steps}"
    )


_HALT_INTENT = "halt_trigger"


class _ReplanThenClickNoSuccessClient:
    """LLM stub for the replan-clears-buffer regression: every step emits a click
    that the dispatcher errors out on (so any_action_succeeded stays False), and
    only step 3's intent triggers supervisor.last_policy='halt' to cause replan.
    """

    def __init__(self):
        self._step = 0

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        if tools is None or _is_planner_call(messages):
            return _plan_stub()
        self._step += 1
        if self._step <= 2:
            tc = ToolCall(
                id=f"tc-pre-{self._step}",
                name="click",
                arguments=json.dumps({"intent": f"erring{self._step}"}),
            )
        elif self._step == 3:
            tc = ToolCall(
                id="tc-halt",
                name="click",
                arguments=json.dumps({"intent": _HALT_INTENT}),
            )
        else:
            tc = ToolCall(
                id=f"tc-post-{self._step}",
                name="click",
                arguments=json.dumps({"intent": f"erring_post{self._step}"}),
            )
        return ChatResponse(
            content=None,
            tool_calls=[tc],
            finish_reason="tool_calls",
            model="fake",
            usage=_DUMMY_USAGE,
            raw={},
        )


def test_replan_clears_no_progress_buffer():
    """Spec: scenario 'replan clears the no_progress buffer'.

    After a supervisor halt+replan, _no_progress_buf must be empty so the
    no_progress bail counter starts fresh from zero. Implementation must NOT
    leave the replan-step's own post-dispatch entry in the buffer.
    """
    stub_browser = _StubBrowser()
    stub_llm = _ReplanThenClickNoSuccessClient()

    def _patched_dispatch(tool_name, args, browser, supervisor, **kwargs):
        intent = args.get("intent", "")
        if intent == _HALT_INTENT:
            supervisor.last_policy = "halt"
            return "Error: element not found after escalation"
        return f"Error: could not find {intent}"

    with (
        patch("agent.loop.observe.build_observation", return_value=_CONSTANT_OBS),
        patch("agent.loop._dispatch", side_effect=_patched_dispatch),
    ):
        result = loop(
            "task",
            browser=stub_browser,
            llm_client=stub_llm,
            max_steps=8,
        )

    assert result.steps >= 7, (
        f"Loop bailed at step {result.steps} with reason={result.reason!r}. "
        f"After replan at step 3, the no_progress window must reset to zero "
        f"so bail cannot fire until step 7 (steps 4+5+6+7 = 4 entries). "
        f"The replan-step's post-dispatch entry must NOT count toward K=4."
    )
