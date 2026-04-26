from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent.llm import ChatResponse, LLMClient

_PLAN_SYSTEM = (
    "You are a planning assistant. Given a task and the current browser state, "
    "produce a short ordered list of steps to complete the task. "
    'Respond with ONLY a JSON object: {"steps": ["step 1", ...], "expected_end_state": "..."}'
)

_REPLAN_SYSTEM = (
    "You are a planning assistant. The prior plan failed partway through. "
    "Given the task, current state, prior steps, and failure reason, "
    "produce a revised short ordered list of steps. "
    'Respond with ONLY a JSON object: {"steps": ["step 1", ...], "expected_end_state": "..."}'
)


@dataclass(frozen=True)
class Plan:
    steps: list[str]
    expected_end_state: str


def _fallback(task: str) -> Plan:
    return Plan(steps=[task], expected_end_state="task complete")


def _parse_plan(content: str | None, task: str) -> Plan:
    if not content:
        return _fallback(task)
    try:
        data = json.loads(content)
        steps = data["steps"]
        if not isinstance(steps, list) or not all(isinstance(s, str) for s in steps):
            return _fallback(task)
        end_state = data.get("expected_end_state", "task complete")
        return Plan(steps=steps, expected_end_state=str(end_state))
    except (json.JSONDecodeError, KeyError, TypeError):
        return _fallback(task)


def plan(task: str, observation: dict, llm: LLMClient) -> tuple[Plan, ChatResponse]:
    messages = [
        {"role": "system", "content": _PLAN_SYSTEM},
        {
            "role": "user",
            "content": f"Task: {task}\n\nCurrent state: {json.dumps(observation)}",
        },
    ]
    response = llm.chat(messages)
    return _parse_plan(response.content, task), response


def replan(
    task: str, observation: dict, prior_plan: Plan, reason: str, llm: LLMClient
) -> tuple[Plan, ChatResponse]:
    prior_steps = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(prior_plan.steps))
    messages = [
        {"role": "system", "content": _REPLAN_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Task: {task}\n\n"
                f"Prior plan steps:\n{prior_steps}\n\n"
                f"Failure reason: {reason}\n\n"
                f"Current state: {json.dumps(observation)}"
            ),
        },
    ]
    response = llm.chat(messages)
    return _parse_plan(response.content, task), response
