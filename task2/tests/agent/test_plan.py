from __future__ import annotations

import dataclasses
import json

import pytest

from agent.llm import ChatResponse, Usage
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


class _FakeLLM:
    def __init__(self, content: str):
        self._content = content

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        return _fake_response(self._content)


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
