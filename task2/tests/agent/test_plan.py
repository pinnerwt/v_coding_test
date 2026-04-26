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
