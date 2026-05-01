from __future__ import annotations

import dataclasses
import json

import pytest

from agent.llm import ChatResponse, ToolCall, Usage
from agent.plan import Plan, plan, replan


def _fake_response(content: str) -> ChatResponse:
    return ChatResponse(
        content=content,
        tool_calls=[],
        finish_reason="stop",
        model="fake",
        usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        raw={},
    )


def _tool_call_response(name: str, arguments: dict, *, call_id: str = "tc-ask") -> ChatResponse:
    return ChatResponse(
        content=None,
        tool_calls=[ToolCall(id=call_id, name=name, arguments=json.dumps(arguments))],
        finish_reason="tool_calls",
        model="fake",
        usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        raw={},
    )


class _FakeLLM:
    def __init__(self, content: str):
        self._content = content

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        return _fake_response(self._content)


class _ScriptedLLM:
    """Returns each scripted ChatResponse in order; records every chat() call."""

    def __init__(self, responses: list[ChatResponse]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        self.calls.append({"messages": list(messages), "tools": tools})
        if not self._responses:
            raise AssertionError("ScriptedLLM exhausted")
        return self._responses.pop(0)


def test_plan_dataclass_is_frozen():
    p = Plan(steps=["step 1", "step 2"], expected_end_state="done")
    assert p.steps == ["step 1", "step 2"]
    assert p.expected_end_state == "done"
    with pytest.raises(dataclasses.FrozenInstanceError):
        p.steps = []  # type: ignore[misc]


def test_plan_returns_plan_from_well_formed_response():
    payload = json.dumps(
        {"steps": ["go to site", "read result"], "expected_end_state": "result found"}
    )
    llm = _FakeLLM(payload)
    result, resp = plan(task="find X", observation={}, llm=llm)
    assert isinstance(result, Plan)
    assert result.steps == ["go to site", "read result"]
    assert result.expected_end_state == "result found"
    assert resp is not None


def test_plan_returns_fallback_on_malformed_json():
    llm = _FakeLLM("not valid json {")
    result, _ = plan(task="find X", observation={}, llm=llm)
    assert result.steps == ["find X"]


def test_plan_returns_fallback_when_steps_key_missing():
    payload = json.dumps({"expected_end_state": "done"})
    llm = _FakeLLM(payload)
    result, _ = plan(task="find X", observation={}, llm=llm)
    assert result.steps == ["find X"]


def test_plan_returns_fallback_when_steps_is_a_string():
    payload = json.dumps({"steps": "go home", "expected_end_state": "done"})
    llm = _FakeLLM(payload)
    result, _ = plan(task="find X", observation={}, llm=llm)
    assert result.steps == ["find X"]


def test_plan_returns_fallback_when_steps_contains_non_strings():
    payload = json.dumps({"steps": [1, 2, 3], "expected_end_state": "done"})
    llm = _FakeLLM(payload)
    result, _ = plan(task="find X", observation={}, llm=llm)
    assert result.steps == ["find X"]


def test_replan_returns_revised_plan_from_well_formed_response():
    payload = json.dumps(
        {"steps": ["try alternative approach"], "expected_end_state": "task done via alt"}
    )
    llm = _FakeLLM(payload)
    prior = Plan(steps=["original step"], expected_end_state="original end")
    result, resp = replan(
        task="find X", observation={}, prior_plan=prior, reason="locate failed", llm=llm
    )
    assert isinstance(result, Plan)
    assert result.steps == ["try alternative approach"]
    assert resp is not None


def test_replan_returns_fallback_on_malformed_json():
    llm = _FakeLLM("not json at all")
    prior = Plan(steps=["original step"], expected_end_state="original end")
    result, _ = replan(task="find X", observation={}, prior_plan=prior, reason="halt", llm=llm)
    assert result.steps == ["find X"]


def test_replan_returns_fallback_when_steps_is_a_string():
    payload = json.dumps({"steps": "go home", "expected_end_state": "done"})
    prior = Plan(steps=["original step"], expected_end_state="original end")
    result, _ = replan(
        task="find X", observation={}, prior_plan=prior, reason="halt", llm=_FakeLLM(payload)
    )
    assert result.steps == ["find X"]


def test_replan_returns_fallback_when_steps_contains_non_strings():
    payload = json.dumps({"steps": [1, 2, 3], "expected_end_state": "done"})
    prior = Plan(steps=["original step"], expected_end_state="original end")
    result, _ = replan(
        task="find X", observation={}, prior_plan=prior, reason="halt", llm=_FakeLLM(payload)
    )
    assert result.steps == ["find X"]


def test_plan_strips_markdown_code_fence_around_json():
    """Qwen3.5-27B sometimes wraps its planner JSON in ```json ... ``` fences;
    _parse_plan must strip these so the real plan is used (not the fallback)."""
    payload = (
        "```json\n"
        '{"steps": ["ask the user: which branch?", "navigate to booking"], '
        '"expected_end_state": "reservation confirmed"}\n'
        "```"
    )
    llm = _FakeLLM(payload)
    result, _ = plan(task="book a table at 旭集", observation={}, llm=llm)
    assert result.steps == ["ask the user: which branch?", "navigate to booking"]
    assert result.expected_end_state == "reservation confirmed"


def test_plan_strips_unlabeled_code_fence_around_json():
    """Bare ``` ... ``` fences (no language tag) must also be stripped."""
    payload = '```\n{"steps": ["a", "b"], "expected_end_state": "done"}\n```'
    llm = _FakeLLM(payload)
    result, _ = plan(task="t", observation={}, llm=llm)
    assert result.steps == ["a", "b"]


def test_replan_strips_markdown_code_fence_around_json():
    payload = '```json\n{"steps": ["c"], "expected_end_state": "done"}\n```'
    prior = Plan(steps=["x"], expected_end_state="x")
    result, _ = replan(
        task="t", observation={}, prior_plan=prior, reason="halt", llm=_FakeLLM(payload)
    )
    assert result.steps == ["c"]


# ---------------------------------------------------------------------------
# planner-side ask_user: when info is insufficient, the planner must call the
# ask_user tool, receive an answer, and then produce the final plan with that
# answer baked in. ask_user is NOT a navigator step in the resulting plan.
# ---------------------------------------------------------------------------


def test_plan_calls_ask_user_callback_when_planner_emits_tool_call():
    """If the planner LLM emits an ask_user tool call, plan() must invoke the
    callback with the question, feed the answer back to the LLM, and then parse
    the LLM's follow-up JSON as the final plan."""
    captured: list[str] = []

    def _cb(q: str) -> str:
        captured.append(q)
        return "Tianmu"

    final_plan_json = json.dumps(
        {
            "steps": [
                "Navigate to https://inline.app/booking/旭集天母",
                "Pick a time slot",
            ],
            "expected_end_state": "reservation confirmed at Tianmu",
        }
    )
    llm = _ScriptedLLM(
        [
            _tool_call_response("ask_user", {"question": "Which 旭集 location?"}, call_id="tc-ask"),
            _fake_response(final_plan_json),
        ]
    )

    result, resp = plan(
        task="book a table at 旭集",
        observation={"url": "about:blank"},
        llm=llm,
        ask_user_callback=_cb,
    )

    assert captured == ["Which 旭集 location?"], (
        f"callback must be invoked once with the planner's question, got {captured!r}"
    )
    assert result.steps == [
        "Navigate to https://inline.app/booking/旭集天母",
        "Pick a time slot",
    ], f"final plan must come from second LLM call, got {result.steps!r}"
    # The second call must include the assistant tool_call message AND the
    # tool-result message carrying the answer, so the LLM can plan around it.
    second_call_msgs = llm.calls[1]["messages"]
    tool_msgs = [m for m in second_call_msgs if m.get("role") == "tool"]
    assert any("Tianmu" in (m.get("content") or "") for m in tool_msgs), (
        f"answer 'Tianmu' must be fed back as a tool message, got {tool_msgs!r}"
    )
    assert resp is not None


def test_plan_does_not_call_ask_user_when_planner_returns_plan_directly():
    """Sufficient-info path: planner returns a JSON plan on the first call,
    callback is never invoked."""
    invoked: list[str] = []

    def _cb(q: str) -> str:
        invoked.append(q)
        return "should not be called"

    payload = json.dumps({"steps": ["go", "read"], "expected_end_state": "done"})
    llm = _ScriptedLLM([_fake_response(payload)])

    result, _ = plan(task="find X", observation={}, llm=llm, ask_user_callback=_cb)

    assert invoked == [], "callback must not be invoked when planner returns plan directly"
    assert result.steps == ["go", "read"]


def test_plan_handles_ask_user_with_no_callback_gracefully():
    """If the planner emits ask_user but no callback is wired, plan() must not
    crash; it should feed back an error tool message and let the planner fall
    back to its best-effort plan on the next turn."""
    payload = json.dumps({"steps": ["best effort", "verify"], "expected_end_state": "done"})
    llm = _ScriptedLLM(
        [
            _tool_call_response("ask_user", {"question": "which?"}, call_id="tc-ask"),
            _fake_response(payload),
        ]
    )

    result, _ = plan(task="t", observation={}, llm=llm, ask_user_callback=None)

    assert result.steps == ["best effort", "verify"]


def test_plan_signature_accepts_ask_user_callback_kwarg():
    """Public surface: plan() must accept ask_user_callback as a keyword arg
    that defaults to None, so existing callers keep working."""
    import inspect

    from agent import plan as plan_mod

    sig = inspect.signature(plan_mod.plan)
    assert "ask_user_callback" in sig.parameters
    p = sig.parameters["ask_user_callback"]
    assert p.default is None


# ---------------------------------------------------------------------------
# Run context: planner sees current date, timezone, locale, and step budget
# ---------------------------------------------------------------------------


def test_plan_renders_run_context_into_user_message():
    """When a RunContext is passed, plan()'s user message must include the
    date, timezone, locale, and step_budget so the planner can plan around
    'now', region-specific entities, and how many navigation steps it has."""
    from agent.plan import RunContext

    payload = json.dumps({"steps": ["go", "read"], "expected_end_state": "done"})
    llm = _ScriptedLLM([_fake_response(payload)])
    ctx = RunContext(
        date="2026-04-30",
        timezone="Asia/Taipei",
        locale="zh-TW",
        step_budget=20,
    )

    plan(task="t", observation={}, llm=llm, context=ctx)

    user_msg = next(m for m in llm.calls[0]["messages"] if m.get("role") == "user")
    content = user_msg["content"]
    assert "2026-04-30" in content
    assert "Asia/Taipei" in content
    assert "zh-TW" in content
    assert "20" in content


def test_plan_signature_accepts_context_kwarg():
    """Public surface: plan() must accept context as a keyword arg that
    defaults to None, so existing callers keep working."""
    import inspect

    from agent import plan as plan_mod

    sig = inspect.signature(plan_mod.plan)
    assert "context" in sig.parameters
    assert sig.parameters["context"].default is None


def test_plan_omits_run_context_block_when_none():
    """When no context is provided, the planner user message must NOT contain
    a 'Run context:' block — preserves the no-context behavior."""
    payload = json.dumps({"steps": ["x", "y"], "expected_end_state": "done"})
    llm = _ScriptedLLM([_fake_response(payload)])

    plan(task="t", observation={}, llm=llm)

    user_msg = next(m for m in llm.calls[0]["messages"] if m.get("role") == "user")
    assert "Run context" not in user_msg["content"]
