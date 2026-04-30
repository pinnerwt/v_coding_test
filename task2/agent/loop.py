from __future__ import annotations

import json
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

import agent.observe as observe
import agent.plan as plan_module
from agent.locate import (
    IntentParseError,
    LocateResult,
    LocatorMiss,
    _canonical_ax_fingerprint,
    locate_l1,
    locate_l2,
    parse_intent,
)
from agent.locator_cache import CacheEntry, _origin_from_url
from agent.supervisor import EscalationDecision, Supervisor
from agent.trace import ActEvent, LocateEvent, PlanEvent, SupervisorEvent, TraceWriter

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from agent.browser import Browser
    from agent.llm import LLMClient
    from agent.locator_cache import LocatorCache

RunStatus = Literal["succeeded", "unverified", "failed", "timeout"]
RunResultReason = Literal["stuck_repeat", "no_tool_call_repeat", "seconds_budget", "no_progress"]
ToolName = Literal["goto", "read", "click", "type", "done", "fail", "ask_user"]
_CLICK_SUCCESS_OUTCOMES: frozenset[str] = frozenset({"ok", "nav"})
_IRRECOVERABLE_REASONS: frozenset[str] = frozenset({"login wall", "captcha", "blocked"})

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
            "name": "click",
            "description": "Click a page element described by intent.",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "Describe the element to click (e.g. 'the Submit button').",
                    }
                },
                "required": ["intent"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "type",
            "description": "Fill a textbox described by intent with text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "intent": {
                        "type": "string",
                        "description": "Describe the textbox to fill (e.g. 'the Email input').",
                    },
                    "text": {
                        "type": "string",
                        "description": "The text to fill into the textbox.",
                    },
                    "submit": {
                        "type": "boolean",
                        "description": (
                            "If true, press Enter after filling. Use only as a "
                            "fallback when a Search/Submit button cannot be "
                            "located via `click`."
                        ),
                    },
                },
                "required": ["intent", "text"],
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
    {
        "type": "function",
        "function": {
            "name": "ask_user",
            "description": (
                "Ask the human a clarifying question and get their answer back as the "
                "tool result. Use only when the task is genuinely ambiguous (e.g. a "
                "named entity has multiple matching locations and there is no way to "
                "infer the intended one from the task text). Do NOT use for things you "
                "can resolve by reading the page."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "A concise question for the user.",
                    }
                },
                "required": ["question"],
            },
        },
    },
]


_DEFAULT_CONTEXT_CHAR_BUDGET: int = 80_000
_STUCK_REPEAT_K: int = 3
_NO_TOOL_CALL_K: int = 3
_NO_PROGRESS_K: int = 4


_ELIDED_AX_TREE_MARKER = "[elided — see latest observation]"
_KEEP_RECENT_AX_TREES = 2


def _strip_stale_ax_trees(messages: list[dict]) -> list[dict]:
    state_indices = [
        i
        for i, m in enumerate(messages)
        if m.get("role") == "user"
        and isinstance(m.get("content"), str)
        and STATE_MESSAGE_PREFIX in m["content"]
    ]
    if len(state_indices) <= _KEEP_RECENT_AX_TREES:
        return messages

    out = list(messages)
    for i in state_indices[:-_KEEP_RECENT_AX_TREES]:
        content = out[i]["content"]
        prefix_idx = content.find(STATE_MESSAGE_PREFIX)
        head = content[: prefix_idx + len(STATE_MESSAGE_PREFIX)]
        json_part = content[prefix_idx + len(STATE_MESSAGE_PREFIX) :]
        try:
            obs = json.loads(json_part)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(obs, dict) or "ax_tree_digest" not in obs:
            continue
        pruned = {k: v for k, v in obs.items() if k != "ax_tree_digest"}
        pruned["ax_tree_digest"] = _ELIDED_AX_TREE_MARKER
        out[i] = {**out[i], "content": head + json.dumps(pruned)}
    return out


def _compact_messages(messages: list[dict], budget_chars: int) -> list[dict]:
    def _is_state_msg(m: dict) -> bool:
        return (
            m.get("role") == "user"
            and isinstance(m.get("content"), str)
            and STATE_MESSAGE_PREFIX in m["content"]
        )

    sizes = [len(json.dumps(m)) for m in messages]
    total = sum(sizes)
    if total <= budget_chars:
        return messages

    last_state_idx: int | None = None
    for i in range(len(messages) - 1, -1, -1):
        if _is_state_msg(messages[i]):
            last_state_idx = i
            break

    if last_state_idx is None:
        return messages

    keep_tail_start = last_state_idx
    drop_idx = 1
    while total > budget_chars and drop_idx < keep_tail_start:
        total -= sizes[drop_idx]
        drop_idx += 1

    while drop_idx < keep_tail_start and not _is_state_msg(messages[drop_idx]):
        drop_idx += 1

    if drop_idx == 1:
        return messages
    return [messages[0]] + messages[drop_idx:]


@dataclass(frozen=True)
class RunResult:
    status: RunStatus
    result: Any
    evidence: dict | None
    verifier: dict | None = None
    reason: RunResultReason | None = None
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


def _phase_breakdown(t0: float, t_llm_start: float, t_dispatch_start: float) -> dict:
    return {
        "observation_ms": int((t_llm_start - t0) * 1000),
        "llm_ms": int((t_dispatch_start - t_llm_start) * 1000),
        "dispatch_ms": int((time.monotonic() - t_dispatch_start) * 1000),
    }


def _record_step(
    step_num: int,
    t0: float,
    response: Any,
    tool_names: list[str],
    per_step: list[int],
    breakdown: list[dict],
    *,
    latency_breakdown: dict,
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
            "latency_breakdown_ms": latency_breakdown,
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


def _build_system_prompt(task: str, *, expect: dict | None = None) -> str:
    base = (
        "You are a browser automation agent. "
        f"Your task is: {task}\n\n"
        "Use the tools provided to navigate the web and gather information. "
        "Bias strongly toward calling `done` early. The MOMENT you can plausibly "
        "answer the task from any page content (a `read` result, the URL, or "
        "visible text), call `done` with that answer. Do NOT continue reading, "
        "clicking, or navigating once a workable answer is visible. "
        "Step budget: you have at most 20 steps. By step 12 you should already "
        "be calling `done` — partial or best-inference answers are acceptable as "
        "long as they are grounded in something you have read. "
        "When a `click` or `type` fails, retry with a refined `intent` or replan "
        "(try a different selector, scroll, or take a different navigation path). "
        "If two clicks fail to advance the task on the current page (no URL "
        "change, no new content), STOP clicking — call `goto` to a different "
        "URL instead (the brand's official site or a fresh search with refined "
        "keywords). Listing/aggregator pages often surface results but rarely "
        "expose the actionable links you need; pivot away. "
        "Only call `done` with a best-effort inference after 2-3 failed retries "
        "and no clearer plan. Always include the current page URL and a text "
        "snippet as evidence in `done`. "
        "If you genuinely run out of budget without finding the answer and "
        "cannot make a grounded best inference, call `fail` with a clear "
        "rationale: where you got stuck, what you tried, and what additional "
        "budget (more steps, different selectors) would enable. Never exceed "
        "the step budget without either a `done` or a `fail`. "
        "Otherwise call `fail` only for irrecoverable conditions — login walls, "
        "captchas, pages that don't exist, or info genuinely absent from the page. "
        "If a target element exists on the page but you don't know how to act on it, "
        "attempt `click`/`type` with a natural-language `intent` first; "
        "the locator pipeline will resolve it. "
        "If a Search/Submit button is not locatable after typing into a search "
        "box, retry the `type` call with `submit=true` to press Enter instead "
        "of clicking a button — do not give up on the search just because the "
        "button can't be found. "
        "AMBIGUITY → ASK, do not guess and do not give up. If the task targets a "
        "named entity (restaurant, store, person, product) and the page reveals "
        "MULTIPLE plausible matches (e.g. several branches/locations of the same "
        "brand) and the task text does not say which one, you MUST call "
        "`ask_user` with a concise clarifying question listing the options. Do "
        "NOT call `done` with a 'cannot determine' answer in this case — that is "
        "a wrong call; `ask_user` is the right call. Do NOT call `fail` either. "
        "After the user answers, continue the task with their choice — do NOT "
        "stop at disambiguation. The original goal still has to be carried "
        "out: if the task asked to book a table, navigate to the brand's "
        "official reservation flow for the chosen branch and attempt to check "
        "availability; if it asked for a product, "
        "navigate to that product page; if it asked a question, find the "
        "answer. Only after pursuing that goal — succeed or hit a real wall — "
        "should you call `done` or `fail`. Use `ask_user` sparingly: only "
        "for genuine ambiguity you cannot resolve by reading more of the page."
    )
    if expect and expect.get("schema"):
        schema = expect["schema"]
        keys = ", ".join(sorted(schema.keys()))
        base += (
            f"\n\nYour `done.result` MUST be a JSON object matching this schema: "
            f"{json.dumps(schema)}. Required fields: {keys}."
        )
    return base


def _body_text(page: Page) -> str:
    return page.evaluate(_BODY_TEXT_JS)[:_BODY_TEXT_LIMIT]


def _locate_via_ladder(
    page: Page,
    intent: str,
    supervisor: Supervisor,
    *,
    trace_writer: TraceWriter | None = None,
    run_id: str | None = None,
    step_id: str | None = None,
) -> LocateResult:
    role, name = parse_intent(intent)
    try:
        return locate_l1(page, role=role, name=name)
    except LocatorMiss as miss:
        if miss.reason != "zero_matches":
            raise
        l1_miss_seq = _emit_locate_event(
            trace_writer=trace_writer,
            run_id=run_id,
            intent=intent,
            tier="L1_ax",
            outcome="miss",
            cache_action=None,
            chosen=None,
            step_id=step_id,
        )
        decision = supervisor.handle(miss, current_tier="L1_ax")
        if l1_miss_seq is not None:
            _emit_supervisor_event(
                trace_writer=trace_writer,
                run_id=run_id,
                decision=decision,
                miss=miss,
                trigger_event_seq=l1_miss_seq,
                step_id=step_id,
            )
        if decision.next_tier != "L2_dom":
            raise
        try:
            result = locate_l2(page, role=role, name=name)
        except LocatorMiss:
            _emit_locate_event(
                trace_writer=trace_writer,
                run_id=run_id,
                intent=intent,
                tier="L2_dom",
                outcome="miss",
                cache_action=None,
                chosen=None,
                step_id=step_id,
            )
            raise
        _emit_locate_event(
            trace_writer=trace_writer,
            run_id=run_id,
            intent=intent,
            tier="L2_dom",
            outcome="hit",
            cache_action=None,
            chosen={"role": result.role, "selector": result.selector},
            step_id=step_id,
        )
        return result


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
) -> int | None:
    if trace_writer is None or run_id is None:
        return None
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
    return seq


def _emit_supervisor_event(
    *,
    trace_writer: TraceWriter | None,
    run_id: str | None,
    decision: EscalationDecision,
    miss: LocatorMiss,
    trigger_event_seq: int,
    step_id: str | None = None,
) -> None:
    if trace_writer is None or run_id is None:
        return
    classified_as = "Ambiguous" if miss.reason == "ambiguous" else "LocatorMiss"
    seq = trace_writer.next_seq(run_id)
    event = SupervisorEvent(
        run_id=run_id,
        seq=seq,
        ts=datetime.now(UTC).isoformat(),
        step_id=step_id,
        trigger_event_seq=trigger_event_seq,
        classified_as=classified_as,
        policy=decision.policy,
        attempt=decision.attempt,
    )
    trace_writer.append_event(event)


def _emit_act_event(
    *,
    trace_writer: TraceWriter | None,
    run_id: str | None,
    tool: str,
    args: dict[str, Any],
    outcome: Literal["ok", "no_effect", "nav", "timeout", "error"],
    ms: int,
    step_id: str | None = None,
) -> None:
    if trace_writer is None or run_id is None:
        return
    seq = trace_writer.next_seq(run_id)
    event = ActEvent(
        run_id=run_id,
        seq=seq,
        ts=datetime.now(UTC).isoformat(),
        step_id=step_id,
        tool=tool,
        args=args,
        outcome=outcome,
        diff={},
        ms=ms,
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
        return _locate_via_ladder(
            page,
            intent,
            supervisor,
            trace_writer=trace_writer,
            run_id=run_id,
            step_id=step_id,
        )

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

    result = _locate_via_ladder(
        page,
        intent,
        supervisor,
        trace_writer=trace_writer,
        run_id=run_id,
        step_id=step_id,
    )

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


def _locate_or_error_msg(
    page: Page,
    intent: str,
    supervisor: Supervisor,
    *,
    cache: LocatorCache | None,
    trace_writer: TraceWriter | None,
    run_id: str | None,
    step_id: str | None,
) -> LocateResult | str:
    try:
        return _locate_with_supervisor(
            page,
            intent,
            supervisor,
            cache=cache,
            trace_writer=trace_writer,
            run_id=run_id,
            step_id=step_id,
        )
    except (LocatorMiss, IntentParseError) as miss:
        return f"Error: could not locate element for intent {intent!r} ({miss})"


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
            located = _locate_or_error_msg(
                page,
                intent,
                supervisor,
                cache=locator_cache,
                trace_writer=trace_writer,
                run_id=run_id,
                step_id=step_id,
            )
            if isinstance(located, str):
                return located
            from agent.browser import ElementNotFound

            try:
                return browser.read(located.selector)
            except ElementNotFound as exc:
                return f"Error: located element vanished before read for intent {intent!r} ({exc})"
        return _body_text(page)
    if tool_name == "click":
        intent_val: str | None = args.get("intent")
        if not isinstance(intent_val, str) or not intent_val:
            return "Error: click requires a non-empty 'intent' string argument"
        page = browser._page
        located = _locate_or_error_msg(
            page,
            intent_val,
            supervisor,
            cache=locator_cache,
            trace_writer=trace_writer,
            run_id=run_id,
            step_id=step_id,
        )
        if isinstance(located, str):
            return located
        locate_result = located
        url_before = page.url
        t_click = time.monotonic()
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        outcome: Literal["ok", "no_effect", "nav", "timeout", "error"]
        try:
            page.locator(locate_result.selector).click(timeout=5000)
        except PlaywrightTimeoutError:
            outcome = "timeout"
        except PlaywrightError:
            outcome = "error"
        else:
            try:
                page.wait_for_load_state("load", timeout=3000)
            except PlaywrightTimeoutError:
                pass
            outcome = "nav" if page.url != url_before else "ok"
        elapsed_ms = int((time.monotonic() - t_click) * 1000)
        _emit_act_event(
            trace_writer=trace_writer,
            run_id=run_id,
            tool="click",
            args={"intent": intent_val},
            outcome=outcome,
            ms=elapsed_ms,
            step_id=step_id,
        )
        if outcome in _CLICK_SUCCESS_OUTCOMES:
            return f"Clicked {intent_val!r} ({outcome})"
        return f"Error: click {outcome} for intent {intent_val!r}"
    if tool_name == "type":
        intent_val = args.get("intent")
        text_val = args.get("text")
        submit_val = bool(args.get("submit", False))
        if not isinstance(intent_val, str) or not intent_val:
            return "Error: type requires a non-empty 'intent' string argument"
        if not isinstance(text_val, str) or not text_val:
            return "Error: type requires a non-empty 'text' string argument"
        page = browser._page
        located = _locate_or_error_msg(
            page,
            intent_val,
            supervisor,
            cache=locator_cache,
            trace_writer=trace_writer,
            run_id=run_id,
            step_id=step_id,
        )
        if isinstance(located, str):
            return located
        locate_result = located
        t_fill = time.monotonic()
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        fill_outcome: Literal["ok", "timeout", "error"]
        locator = page.locator(locate_result.selector)
        try:
            locator.fill(text_val, timeout=5000)
        except PlaywrightTimeoutError:
            fill_outcome = "timeout"
        except PlaywrightError:
            fill_outcome = "error"
        else:
            fill_outcome = "ok"
            if submit_val:
                try:
                    locator.press("Enter", timeout=5000)
                    try:
                        page.wait_for_load_state("load", timeout=3000)
                    except PlaywrightTimeoutError:
                        pass
                except (PlaywrightTimeoutError, PlaywrightError):
                    pass
        elapsed_ms = int((time.monotonic() - t_fill) * 1000)
        emit_args: dict = {"intent": intent_val, "text": text_val}
        if submit_val:
            emit_args["submit"] = True
        _emit_act_event(
            trace_writer=trace_writer,
            run_id=run_id,
            tool="type",
            args=emit_args,
            outcome=fill_outcome,
            ms=elapsed_ms,
            step_id=step_id,
        )
        if fill_outcome == "ok":
            return f"Typed into {intent_val!r} (ok)"
        return f"Error: type {fill_outcome} for intent {intent_val!r}"
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
    expect: dict | None = None,
    budget_seconds: float | None = None,
    ask_user_callback: Callable[[str], str] | None = None,
) -> RunResult:
    if trace_writer is not None and run_id is None:
        raise ValueError("run_id is required when trace_writer is provided")
    messages: list[dict] = [
        {"role": "system", "content": _build_system_prompt(task, expect=expect)}
    ]
    supervisor = Supervisor()

    cum_prompt_tokens = 0
    cum_completion_tokens = 0
    cum_usd = 0.0
    latency_ms_per_step: list[int] = []
    step_breakdown: list[dict] = []
    step_num = 0
    last_actions: list[dict] = []
    active_plan: plan_module.Plan | None = None
    _prior_act_outcomes: list[str] = []
    _stuck_buf: list[str] = []
    _no_progress_buf: list[tuple[str | None, bool]] = []
    _consecutive_no_tool_call_steps: int = 0
    _force_done_next: bool = False
    _no_progress_warned: bool = False
    _budget = int(os.environ.get("LLM_CONTEXT_CHAR_BUDGET", _DEFAULT_CONTEXT_CHAR_BUDGET))
    t_loop = time.monotonic()

    for _ in range(max_steps):
        if budget_seconds is not None and (time.monotonic() - t_loop) >= budget_seconds:
            return RunResult(
                status="timeout",
                reason="seconds_budget",
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
        step_num += 1
        t0 = time.monotonic()
        _step_id = f"{run_id}:step-{step_num}" if run_id is not None else None
        any_action_succeeded_this_step: bool = False
        replanned_this_step: bool = False

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
        budget_prefix = ""
        steps_remaining = max_steps - step_num
        time_used = time.monotonic() - t_loop
        time_frac = time_used / budget_seconds if budget_seconds else 0.0
        if _force_done_next or steps_remaining <= 4 or time_frac >= 0.65:
            budget_prefix = (
                f"URGENT: step {step_num}/{max_steps}, time used "
                f"{time_used:.0f}s. Stop navigating. Call `done` NOW with your "
                "best-effort answer based on anything you have already read — "
                "even a partial or uncertain answer is acceptable. ONLY call "
                "`fail` if you have literally read nothing relevant; in that "
                "case explain where you got stuck, what you tried, and what "
                "additional budget would enable. Do not call any other tool.\n\n"
            )
        else:
            budget_prefix = f"Step {step_num}/{max_steps}.\n\n"
        _force_done_next = False
        messages.append(
            {
                "role": "user",
                "content": (
                    f"{budget_prefix}{plan_prefix}{STATE_MESSAGE_PREFIX}{json.dumps(observation)}"
                ),
            }
        )

        if events is not None:
            events.append(_DecisionMarker())

        messages = _strip_stale_ax_trees(messages)
        messages = _compact_messages(messages, _budget)
        t_llm_start = time.monotonic()
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

        t_dispatch_start = time.monotonic()

        if not response.tool_calls:
            _consecutive_no_tool_call_steps += 1
            _record_step(
                step_num,
                t0,
                response,
                [],
                latency_ms_per_step,
                step_breakdown,
                latency_breakdown=_phase_breakdown(t0, t_llm_start, t_dispatch_start),
            )
            if _consecutive_no_tool_call_steps >= _NO_TOOL_CALL_K:
                return RunResult(
                    status="failed",
                    reason="no_tool_call_repeat",
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
            continue

        _consecutive_no_tool_call_steps = 0
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
                    latency_breakdown=_phase_breakdown(t0, t_llm_start, t_dispatch_start),
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
                reason = args.get("reason", "")
                is_irrecoverable = any(kw in reason.lower() for kw in _IRRECOVERABLE_REASONS)
                is_premature = step_num <= 1 and not _prior_act_outcomes and not is_irrecoverable
                if is_premature:
                    use_writer = trace_writer is not None and run_id is not None
                    sup_seq = trace_writer.next_seq(run_id) if use_writer else 0
                    sup_event = SupervisorEvent(
                        run_id=run_id if use_writer else "loop",
                        seq=sup_seq,
                        ts=datetime.now(UTC).isoformat() if use_writer else "",
                        step_id=_step_id,
                        trigger_event_seq=0,
                        classified_as="premature_fail",
                        policy="halt",
                        attempt=1,
                    )
                    if use_writer:
                        trace_writer.append_event(sup_event)
                    elif events is not None:
                        events.append(sup_event)
                    nudge = (
                        f"you have {max_steps - step_num} steps left and have not attempted "
                        "to interact — try `click`/`type` first."
                    )
                    messages.append(
                        {"role": "tool", "tool_call_id": tool_call.id, "content": nudge}
                    )
                    continue
                _record_step(
                    step_num,
                    t0,
                    response,
                    dispatched_tool_names,
                    latency_ms_per_step,
                    step_breakdown,
                    latency_breakdown=_phase_breakdown(t0, t_llm_start, t_dispatch_start),
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

            if tool_call.name == "ask_user":
                question = args.get("question")
                if not isinstance(question, str) or not question.strip():
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": ("Error: ask_user requires a non-empty 'question' string."),
                        }
                    )
                    continue
                if ask_user_callback is None:
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": (
                                "Error: ask_user is not available in this run "
                                "(no callback wired). Resolve the ambiguity from "
                                "page content or call `done`/`fail`."
                            ),
                        }
                    )
                    continue
                try:
                    answer = ask_user_callback(question)
                except Exception as exc:  # noqa: BLE001
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": f"Error: ask_user callback raised: {exc}",
                        }
                    )
                    continue
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": str(answer),
                    }
                )
                continue

            _sup_calls_before = supervisor.total_attempts()
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
            if supervisor.total_attempts() > _sup_calls_before:
                _stuck_buf.clear()
            _stuck_buf.append(f"{tool_call.name}:{json.dumps(args, sort_keys=True)}")
            if len(_stuck_buf) > _STUCK_REPEAT_K:
                _stuck_buf.pop(0)
            if len(_stuck_buf) == _STUCK_REPEAT_K and len(set(_stuck_buf)) == 1:
                _record_step(
                    step_num,
                    t0,
                    response,
                    dispatched_tool_names,
                    latency_ms_per_step,
                    step_breakdown,
                    latency_breakdown=_phase_breakdown(t0, t_llm_start, t_dispatch_start),
                )
                return RunResult(
                    status="failed",
                    reason="stuck_repeat",
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

            is_error = tool_result.startswith("Error:")
            if tool_call.name in {"click", "type"} and not is_error:
                _prior_act_outcomes.append("ok")
                any_action_succeeded_this_step = True
            elif tool_call.name in {"goto", "read"} and not is_error:
                any_action_succeeded_this_step = True
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
                    _no_progress_buf.clear()
                    replanned_this_step = True
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
                        latency_breakdown=_phase_breakdown(t0, t_llm_start, t_dispatch_start),
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

        if not replanned_this_step:
            _post_obs = observe.build_observation(browser, [])
            post_fp = _post_obs.get("ax_fingerprint") if isinstance(_post_obs, dict) else None
            _no_progress_buf.append((post_fp, any_action_succeeded_this_step))
            if len(_no_progress_buf) > _NO_PROGRESS_K:
                _no_progress_buf.pop(0)
            fps = {fp for fp, _ in _no_progress_buf}
            if (
                len(_no_progress_buf) == _NO_PROGRESS_K
                and len(fps) == 1
                and None not in fps
                and all(not ok for _, ok in _no_progress_buf)
            ):
                if not _no_progress_warned:
                    _force_done_next = True
                    _no_progress_warned = True
                    _no_progress_buf.clear()
                else:
                    _record_step(
                        step_num,
                        t0,
                        response,
                        dispatched_tool_names,
                        latency_ms_per_step,
                        step_breakdown,
                        latency_breakdown=_phase_breakdown(t0, t_llm_start, t_dispatch_start),
                    )
                    return RunResult(
                        status="failed",
                        reason="no_progress",
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
            latency_breakdown=_phase_breakdown(t0, t_llm_start, t_dispatch_start),
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
