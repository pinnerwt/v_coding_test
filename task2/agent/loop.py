from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from agent.locate import locate

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from agent.browser import Browser
    from agent.llm import LLMClient

RunStatus = Literal["succeeded", "failed", "timeout"]
ToolName = Literal["goto", "read", "done", "fail"]

_BODY_TEXT_JS = "() => document.body.innerText"
_BODY_TEXT_LIMIT = 2000

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
    status: RunStatus
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


def _body_text(page: Page) -> str:
    return page.evaluate(_BODY_TEXT_JS)[:_BODY_TEXT_LIMIT]


def _observe(browser: Browser) -> dict:
    page = browser._page
    if page is None:
        return {"url": "", "text": ""}
    return {"url": page.url, "text": _body_text(page)}


def _dispatch(tool_name: str, args: dict, browser: Browser) -> str:
    if tool_name == "goto":
        browser.goto(args["url"])
        return f"Navigated to {args['url']}"
    if tool_name == "read":
        intent: str | None = args.get("intent")
        page = browser._page
        if intent:
            return browser.read(locate(page, intent).selector)
        return _body_text(page)
    raise ValueError(f"Unknown tool: {tool_name!r}")


def loop(
    task: str,
    browser: Browser,
    llm_client: LLMClient,
    *,
    max_steps: int = 20,
) -> RunResult:
    messages: list[dict] = [{"role": "system", "content": _build_system_prompt(task)}]

    for _ in range(max_steps):
        observation = _observe(browser)
        messages.append({"role": "user", "content": f"Current state: {json.dumps(observation)}"})

        response = llm_client.chat(messages, tools=TOOLS)

        assistant_msg: dict[str, Any] = {"role": "assistant", "content": response.content}
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

            tool_result = _dispatch(tool_call.name, args, browser)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                }
            )

    return RunResult(status="timeout", result=None, evidence=None)
