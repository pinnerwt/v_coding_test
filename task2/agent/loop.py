from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

import agent.observe as observe
import agent.plan as plan_module
from agent.locate import (
    LocateResult,
    LocatorMiss,
    _canonical_ax_fingerprint,
    locate_l1,
    locate_l2,
    parse_intent,
)
from agent.locator_cache import CacheEntry, _origin_from_url
from agent.supervisor import Supervisor
from agent.trace import LocateEvent, PlanEvent, TraceWriter

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from agent.browser import Browser
    from agent.llm import LLMClient
    from agent.locator_cache import LocatorCache

RunStatus = Literal["succeeded", "unverified", "failed", "timeout"]
ToolName = Literal["goto", "read", "done", "fail"]

STATE_MESSAGE_PREFIX = "Current state: "

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
    verifier: dict | None = None
    steps: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    usd: float = 0.0
    latency_ms_total: int = 0
    latency_ms_per_step: list[int] = field(default_factory=list)
    step_breakdown: list[dict] = field(default_factory=list)


@dataclass
class _DecisionMarker:
    kind: str = "decision"


def _record_step(
    step_num: int,
    t0: float,
    response: Any,
    tool_names: list[str],
    per_step: list[int],
    breakdown: list[dict],
) -> int:
    step_ms = int((time.monotonic() - t0) * 1000)
    per_step.append(step_ms)
    breakdown.append(
        {
            "step": step_num,
            "latency_ms": step_ms,
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "usd": response.usd,
            "tool_calls": tool_names,
        }
    )
    return step_ms


def _check_evidence(evidence: dict | None) -> dict:
    reasons: list[str] = []
    if not isinstance(evidence, dict):
        reasons.append("evidence.url is missing or empty")
        reasons.append("evidence.text_snippet is missing or empty")
    else:
        url = evidence.get("url")
        if not isinstance(url, str) or not url.strip():
            reasons.append("evidence.url is missing or empty")
        text_snippet = evidence.get("text_snippet")
        if not isinstance(text_snippet, str) or not text_snippet.strip():
            reasons.append("evidence.text_snippet is missing or empty")
    return {"ok": len(reasons) == 0, "reasons": reasons}


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


def _locate_via_ladder(page: Page, intent: str, supervisor: Supervisor) -> LocateResult:
    role, name = parse_intent(intent)
    try:
        return locate_l1(page, role=role, name=name)
    except LocatorMiss as miss:
        if miss.reason != "zero_matches":
            raise
        decision = supervisor.handle(miss, current_tier="L1_ax")
        if decision.next_tier != "L2_dom":
            raise
        return locate_l2(page, role=role, name=name)


def _emit_locate_event(
    *,
    trace_writer: TraceWriter | None,
    run_id: str | None,
    intent: str,
    tier: Literal["cache", "L1_ax", "L2_dom", "L3_rerank", "L4_vision"],
    outcome: Literal["hit", "miss", "ambiguous", "error"],
    cache_action: Literal["read", "write", "invalidate"] | None,
    chosen: dict[str, Any] | None,
    step_id: str | None = None,
) -> None:
    if trace_writer is None or run_id is None:
        return
    seq = trace_writer.next_seq(run_id)
    event = LocateEvent(
        run_id=run_id,
        seq=seq,
        ts=datetime.now(UTC).isoformat(),
        step_id=step_id,
        intent=intent,
        tier=tier,
        outcome=outcome,
        candidates=[],
        chosen=chosen,
        cache_action=cache_action,
        ms=0,
    )
    trace_writer.append_event(event)


def _locate_with_supervisor(
    page: Page,
    intent: str,
    supervisor: Supervisor,
    *,
    cache: LocatorCache | None = None,
    trace_writer: TraceWriter | None = None,
    run_id: str | None = None,
    step_id: str | None = None,
) -> LocateResult:
    if cache is None:
        return _locate_via_ladder(page, intent, supervisor)

    origin = _origin_from_url(page.url)
    entry = cache.get(origin=origin, intent=intent)
    if entry is not None:
        if entry.tier == "L4_vision":
            cache.invalidate(origin=origin, intent=intent)
            _emit_locate_event(
                trace_writer=trace_writer,
                run_id=run_id,
                intent=intent,
                tier="cache",
                outcome="miss",
                cache_action="invalidate",
                chosen=None,
                step_id=step_id,
            )
        else:
            live_fp = _canonical_ax_fingerprint(page, role=entry.role, selector=entry.selector)
            if live_fp is None or live_fp != entry.ax_fingerprint:
                cache.invalidate(origin=origin, intent=intent)
                _emit_locate_event(
                    trace_writer=trace_writer,
                    run_id=run_id,
                    intent=intent,
                    tier="cache",
                    outcome="miss",
                    cache_action="invalidate",
                    chosen=None,
                    step_id=step_id,
                )
            else:
                _emit_locate_event(
                    trace_writer=trace_writer,
                    run_id=run_id,
                    intent=intent,
                    tier="cache",
                    outcome="hit",
                    cache_action="read",
                    chosen={
                        "role": entry.role,
                        "selector": entry.selector,
                        "ax_fingerprint": entry.ax_fingerprint,
                    },
                    step_id=step_id,
                )
                return LocateResult(
                    tier="cache",
                    role=entry.role,
                    name=entry.name,
                    selector=entry.selector,
                    ax_fingerprint=entry.ax_fingerprint,
                    confidence=entry.confidence,
                    coords=entry.coords,
                )

    result = _locate_via_ladder(page, intent, supervisor)

    if result.tier == "L4_vision":
        stored_fingerprint = result.ax_fingerprint
    else:
        canonical = _canonical_ax_fingerprint(page, role=result.role, selector=result.selector)
        stored_fingerprint = canonical if canonical is not None else result.ax_fingerprint
    written_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    cache.put(
        CacheEntry(
            origin=origin,
            intent=intent,
            role=result.role,
            name=result.name,
            selector=result.selector,
            ax_fingerprint=stored_fingerprint,
            confidence=result.confidence,
            tier=result.tier,
            coords=result.coords,
            written_at_utc=written_at,
        )
    )
    _emit_locate_event(
        trace_writer=trace_writer,
        run_id=run_id,
        intent=intent,
        tier=result.tier,
        outcome="hit",
        cache_action="write",
        chosen={
            "role": result.role,
            "selector": result.selector,
            "ax_fingerprint": stored_fingerprint,
        },
        step_id=step_id,
    )
    return result


def _dispatch(
    tool_name: str,
    args: dict,
    browser: Browser,
    supervisor: Supervisor,
    *,
    locator_cache: LocatorCache | None = None,
    trace_writer: TraceWriter | None = None,
    run_id: str | None = None,
    step_id: str | None = None,
) -> str:
    if tool_name == "goto":
        url = args.get("url")
        if not isinstance(url, str) or not url:
            return "Error: goto requires a non-empty 'url' string argument"
        browser.goto(url)
        return f"Navigated to {url}"
    if tool_name == "read":
        intent: str | None = args.get("intent")
        page = browser._page
        if intent:
            try:
                locate_result = _locate_with_supervisor(
                    page,
                    intent,
                    supervisor,
                    cache=locator_cache,
                    trace_writer=trace_writer,
                    run_id=run_id,
                    step_id=step_id,
                )
            except LocatorMiss as miss:
                return f"Error: could not locate element for intent {intent!r} ({miss})"
            from agent.browser import ElementNotFound

            try:
                return browser.read(locate_result.selector)
            except ElementNotFound as exc:
                return f"Error: located element vanished before read for intent {intent!r} ({exc})"
        return _body_text(page)
    return f"Error: unknown tool {tool_name!r}"


def _emit_plan_event(
    events: list | None,
    reason: Literal["initial", "replan"],
    steps: list[str],
    call_id: str,
    trace_writer: TraceWriter | None = None,
    run_id: str | None = None,
    step_id: str | None = None,
) -> None:
    use_writer = trace_writer is not None and run_id is not None
    seq = trace_writer.next_seq(run_id) if use_writer else 0
    event = PlanEvent(
        run_id=run_id if use_writer else "loop",
        seq=seq,
        ts=datetime.now(UTC).isoformat() if use_writer else "",
        step_id=step_id,
        reason=reason,
        steps=steps,
        llm_call_id=call_id,
    )
    if use_writer:
        trace_writer.append_event(event)
        return
    if events is None:
        return
    events.append(event)


def _plan_progress_block(steps: list[str]) -> str:
    lines = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))
    return f"Plan progress:\n{lines}\n\n"


def loop(
    task: str,
    browser: Browser,
    llm_client: LLMClient,
    *,
    max_steps: int = 20,
    events: list | None = None,
    run_id: str | None = None,
    trace_writer: TraceWriter | None = None,
    locator_cache: LocatorCache | None = None,
) -> RunResult:
    if trace_writer is not None and run_id is None:
        raise ValueError("run_id is required when trace_writer is provided")
    messages: list[dict] = [{"role": "system", "content": _build_system_prompt(task)}]
    supervisor = Supervisor()

    cum_prompt_tokens = 0
    cum_completion_tokens = 0
    cum_usd = 0.0
    latency_ms_per_step: list[int] = []
    step_breakdown: list[dict] = []
    step_num = 0
    last_actions: list[dict] = []
    active_plan: plan_module.Plan | None = None

    for _ in range(max_steps):
        step_num += 1
        t0 = time.monotonic()
        _step_id = f"{run_id}:step-{step_num}" if run_id is not None else None

        observation = observe.build_observation(browser, last_actions)
        last_actions = []

        if step_num == 1:
            active_plan, plan_resp = plan_module.plan(task, observation, llm_client)
            cum_prompt_tokens += plan_resp.usage.prompt_tokens
            cum_completion_tokens += plan_resp.usage.completion_tokens
            cum_usd += plan_resp.usd
            _emit_plan_event(
                events,
                "initial",
                active_plan.steps,
                str(uuid.uuid4()),
                trace_writer=trace_writer,
                run_id=run_id,
                step_id=_step_id,
            )

        assert active_plan is not None
        plan_prefix = _plan_progress_block(active_plan.steps)
        messages.append(
            {
                "role": "user",
                "content": f"{plan_prefix}{STATE_MESSAGE_PREFIX}{json.dumps(observation)}",
            }
        )

        if events is not None:
            events.append(_DecisionMarker())

        response = llm_client.chat(messages, tools=TOOLS)

        cum_prompt_tokens += response.usage.prompt_tokens
        cum_completion_tokens += response.usage.completion_tokens
        cum_usd += response.usd

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

        dispatched_tool_names: list[str] = []

        if not response.tool_calls:
            _record_step(step_num, t0, response, [], latency_ms_per_step, step_breakdown)
            continue

        for tool_call in response.tool_calls:
            dispatched_tool_names.append(tool_call.name)
            try:
                args = json.loads(tool_call.arguments) if tool_call.arguments else {}
            except json.JSONDecodeError as exc:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"Error: invalid JSON arguments ({exc.msg})",
                    }
                )
                continue

            if not isinstance(args, dict):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": (
                            "Error: tool arguments must be a JSON object, "
                            f"got {type(args).__name__}"
                        ),
                    }
                )
                continue

            if tool_call.name == "done":
                evidence = args.get("evidence")
                verifier = _check_evidence(evidence)
                status: RunStatus = "succeeded" if verifier["ok"] else "unverified"
                _record_step(
                    step_num,
                    t0,
                    response,
                    dispatched_tool_names,
                    latency_ms_per_step,
                    step_breakdown,
                )
                return RunResult(
                    status=status,
                    result=args.get("result"),
                    evidence=evidence,
                    verifier=verifier,
                    steps=step_num,
                    prompt_tokens=cum_prompt_tokens,
                    completion_tokens=cum_completion_tokens,
                    usd=cum_usd,
                    latency_ms_total=sum(latency_ms_per_step),
                    latency_ms_per_step=latency_ms_per_step,
                    step_breakdown=step_breakdown,
                )
            if tool_call.name == "fail":
                _record_step(
                    step_num,
                    t0,
                    response,
                    dispatched_tool_names,
                    latency_ms_per_step,
                    step_breakdown,
                )
                return RunResult(
                    status="failed",
                    result=None,
                    evidence=None,
                    verifier=None,
                    steps=step_num,
                    prompt_tokens=cum_prompt_tokens,
                    completion_tokens=cum_completion_tokens,
                    usd=cum_usd,
                    latency_ms_total=sum(latency_ms_per_step),
                    latency_ms_per_step=latency_ms_per_step,
                    step_breakdown=step_breakdown,
                )

            tool_result = _dispatch(
                tool_call.name,
                args,
                browser,
                supervisor,
                locator_cache=locator_cache,
                trace_writer=trace_writer,
                run_id=run_id,
                step_id=_step_id,
            )

            is_error = tool_result.startswith("Error:")
            action: dict = {
                "tool": tool_call.name,
                "intent": str(args),
                "outcome": "error" if is_error else "ok",
            }
            if is_error:
                action["error"] = tool_result
            last_actions.append(action)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                }
            )

            if is_error and supervisor.last_policy == "halt":
                supervisor.last_policy = None
                if not supervisor.replan_used:
                    new_plan, replan_resp = plan_module.replan(
                        task, observation, active_plan, tool_result, llm_client
                    )
                    cum_prompt_tokens += replan_resp.usage.prompt_tokens
                    cum_completion_tokens += replan_resp.usage.completion_tokens
                    cum_usd += replan_resp.usd
                    supervisor.replan_used = True
                    active_plan = new_plan
                    _emit_plan_event(
                        events,
                        "replan",
                        new_plan.steps,
                        str(uuid.uuid4()),
                        trace_writer=trace_writer,
                        run_id=run_id,
                        step_id=_step_id,
                    )
                    break
                else:
                    _record_step(
                        step_num,
                        t0,
                        response,
                        dispatched_tool_names,
                        latency_ms_per_step,
                        step_breakdown,
                    )
                    return RunResult(
                        status="failed",
                        result=None,
                        evidence=None,
                        verifier=None,
                        steps=step_num,
                        prompt_tokens=cum_prompt_tokens,
                        completion_tokens=cum_completion_tokens,
                        usd=cum_usd,
                        latency_ms_total=sum(latency_ms_per_step),
                        latency_ms_per_step=latency_ms_per_step,
                        step_breakdown=step_breakdown,
                    )

        _record_step(
            step_num,
            t0,
            response,
            dispatched_tool_names,
            latency_ms_per_step,
            step_breakdown,
        )

    return RunResult(
        status="timeout",
        result=None,
        evidence=None,
        steps=step_num,
        prompt_tokens=cum_prompt_tokens,
        completion_tokens=cum_completion_tokens,
        usd=cum_usd,
        latency_ms_total=sum(latency_ms_per_step),
        latency_ms_per_step=latency_ms_per_step,
        step_breakdown=step_breakdown,
    )
