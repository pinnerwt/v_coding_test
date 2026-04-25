from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from agent.locate import locate

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "goto",
            "description": "Navigate the browser to a URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Absolute URL to navigate to"}
                },
                "required": ["url"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": (
                "Read visible text from the page, optionally targeting an element by intent "
                "(e.g. 'the article heading'). Returns the text content."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": (
                            "Optional: describe which element to read "
                            "(e.g. 'the search result heading'). "
                            "Omit to read the full page body."
                        ),
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": "Mark the task as complete and return the result with evidence.",
            "parameters": {
                "type": "object",
                "properties": {
                    "result": {
                        "type": "object",
                        "description": "Structured result data from the task",
                    },
                    "evidence": {
                        "type": "object",
                        "description": (
                            "Evidence supporting the result. "
                            "MUST include 'url' (string) and 'text_snippet' (string)."
                        ),
                        "properties": {
                            "url": {"type": "string"},
                            "text_snippet": {"type": "string"},
                        },
                        "required": ["url", "text_snippet"],
                    },
                },
                "required": ["result", "evidence"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fail",
            "description": (
                "Mark the task as failed with a reason (e.g. login wall, captcha, page not found)."
            ),
            "parameters": {
                "type": "object",
                "properties": {"reason": {"type": "string"}},
                "required": ["reason"],
            },
        },
    },
]


@dataclass(frozen=True)
class RunResult:
    status: str
    result: Any
    evidence: dict | None


def _build_system_prompt(task: str) -> str:
    return (
        "You are a browser automation agent. "
        f"Your task is: {task}\n\n"
        "Use the tools provided to navigate the web and gather information. "
        "When you have completed the task, call the `done` tool with a structured result "
        "and evidence (including the current page URL and a text snippet confirming the result). "
        "If you cannot complete the task, call `fail` with a reason."
    )


def _observe(browser: Any) -> dict:
    page = browser._page
    if page is None:
        return {"url": "", "text": ""}
    url: str = page.url
    text: str = page.evaluate("() => document.body.innerText")[:2000]
    return {"url": url, "text": text}


def _dispatch(tool_name: str, args: dict, browser: Any) -> str:
    if tool_name == "goto":
        browser.goto(args["url"])
        return f"Navigated to {args['url']}"
    if tool_name == "read":
        intent: str | None = args.get("intent")
        page = browser._page
        if intent:
            locate_result = locate(page, intent)
            return browser.read(locate_result.selector)
        return page.evaluate("() => document.body.innerText")[:2000]
    return f"Unknown tool: {tool_name}"


def loop(
    task: str,
    browser: Any,
    llm_client: Any,
    *,
    max_steps: int = 20,
) -> RunResult:
    messages: list[dict] = [{"role": "system", "content": _build_system_prompt(task)}]

    for _ in range(max_steps):
        # Observe current state.
        observation = _observe(browser)
        messages.append({"role": "user", "content": f"Current state: {json.dumps(observation)}"})

        # Ask the LLM what to do next.
        response = llm_client.chat(messages, tools=TOOLS)

        # Build the assistant message to append to history.
        assistant_msg: dict[str, Any] = {"role": "assistant"}
        if response.content:
            assistant_msg["content"] = response.content
        else:
            assistant_msg["content"] = None
        if response.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in response.tool_calls
            ]
        messages.append(assistant_msg)

        if not response.tool_calls:
            # Model returned text only — continue to next step.
            continue

        for tool_call in response.tool_calls:
            args = json.loads(tool_call.arguments) if tool_call.arguments else {}

            if tool_call.name == "done":
                return RunResult(
                    status="succeeded",
                    result=args.get("result"),
                    evidence=args.get("evidence"),
                )
            if tool_call.name == "fail":
                return RunResult(status="failed", result=None, evidence=None)

            # Non-terminal tool — execute and feed result back.
            tool_result = _dispatch(tool_call.name, args, browser)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                }
            )

    return RunResult(status="timeout", result=None, evidence=None)
