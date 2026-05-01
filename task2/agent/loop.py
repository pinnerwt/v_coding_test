from __future__ import annotations

import json
import os
import re
import time
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

import agent.observe as observe
import agent.plan as plan_module
from agent.locate import (
    IntentParseError,
    LocateResult,
    LocatorMiss,
)
from agent.supervisor import EscalationDecision, Supervisor
from agent.trace import (
    ActEvent,
    LocateEvent,
    PlanEvent,
    StepAdvanceEvent,
    SupervisorEvent,
    TraceWriter,
)

if TYPE_CHECKING:
    from playwright.sync_api import Page

    from agent.browser import Browser
    from agent.llm import LLMClient
    from agent.locator_cache import LocatorCache

RunStatus = Literal["succeeded", "unverified", "failed", "timeout"]
RunResultReason = Literal["stuck_repeat", "no_tool_call_repeat", "seconds_budget", "no_progress"]
ToolName = Literal["goto", "read", "click", "type", "done", "fail"]
_CLICK_SUCCESS_OUTCOMES: frozenset[str] = frozenset({"ok", "nav"})
_IRRECOVERABLE_REASONS: frozenset[str] = frozenset({"login wall", "captcha", "blocked"})

STATE_MESSAGE_PREFIX = "Current state: "

_BODY_TEXT_JS = "() => document.body.innerText"
_BODY_TEXT_LIMIT = 2000

# T4 plan-progress pointer: every non-terminal action tool advertises
# `plan_cursor` so the LLM has to declare which plan step it's executing.
# Two consecutive off-plan declarations auto-trigger a replan.
_PLAN_CURSOR_PROPERTY: dict = {
    "description": (
        "1-based index of the current plan step you're executing, or the "
        'literal string "off-plan" if no current plan step matches what '
        "you're doing (in which case set plan_cursor_reason)."
    ),
    "anyOf": [
        {"type": "integer", "minimum": 1},
        {"type": "string", "enum": ["off-plan"]},
    ],
}
_PLAN_CURSOR_REASON_PROPERTY: dict = {
    "type": "string",
    "description": (
        'When plan_cursor="off-plan", briefly explain why no plan step '
        "applies. Two consecutive off-plan declarations will trigger a "
        "supervisor-initiated replan."
    ),
}

TOOLS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "goto",
            "description": "Navigate the browser to a URL.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "Absolute URL to navigate to"},
                    "plan_cursor": _PLAN_CURSOR_PROPERTY,
                    "plan_cursor_reason": _PLAN_CURSOR_REASON_PROPERTY,
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
                "Read visible text from the page. With no args, returns the first ~2000 "
                "chars of body text. Use 'intent' to target an element (e.g. 'the article "
                "heading'). Use 'find' to return a window of text centered on the first "
                "occurrence of a substring (case-insensitive) — useful when the answer "
                "sits past the default window on a long page (e.g. a Wikipedia article)."
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
                    },
                    "find": {
                        "type": "string",
                        "description": (
                            "Optional: a substring (case-insensitive) to locate in the "
                            "full body text; returns ~2000 chars of surrounding context. "
                            "Mutually exclusive with 'intent'."
                        ),
                    },
                    "plan_cursor": _PLAN_CURSOR_PROPERTY,
                    "plan_cursor_reason": _PLAN_CURSOR_REASON_PROPERTY,
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
                    "evaluation_previous_action": {
                        "type": "string",
                        "enum": ["success", "partial", "failed", "no_action_yet"],
                        "description": (
                            "Self-eval of the most recent tool call before this `done`. "
                            "Use 'no_action_yet' ONLY when literally no click/type/select "
                            "has happened in this run — in which case you almost certainly "
                            "should not be calling `done` yet."
                        ),
                    },
                    "evaluation_reason": {
                        "type": "string",
                        "description": (
                            "One-sentence justification for evaluation_previous_action, "
                            "grounded in observed page changes."
                        ),
                    },
                    "next_goal": {
                        "type": "string",
                        "description": (
                            "What this `done` is for. For a real terminal call this should "
                            "be a reporting phrase like 'report the final answer'. If you "
                            "find yourself writing a navigation/search verb here (search, "
                            "navigate, click, find, look up, fill in), you are not done — "
                            "call the appropriate tool instead."
                        ),
                    },
                },
                "required": [
                    "result",
                    "evidence",
                    "evaluation_previous_action",
                    "evaluation_reason",
                    "next_goal",
                ],
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
                    },
                    "plan_cursor": _PLAN_CURSOR_PROPERTY,
                    "plan_cursor_reason": _PLAN_CURSOR_REASON_PROPERTY,
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
                    "plan_cursor": _PLAN_CURSOR_PROPERTY,
                    "plan_cursor_reason": _PLAN_CURSOR_REASON_PROPERTY,
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
]


_DEFAULT_CONTEXT_CHAR_BUDGET: int = 80_000
_STUCK_REPEAT_K: int = 3
_NO_TOOL_CALL_K: int = 3
_NO_PROGRESS_K: int = 4
# T4: how many consecutive off-plan steps trigger an auto-replan.
_OFF_PLAN_REPLAN_THRESHOLD: int = 2
# T4: action tools that carry plan_cursor / plan_cursor_reason.
_PLAN_CURSOR_TOOLS: frozenset[str] = frozenset({"goto", "click", "type", "read"})
# F5: result.status values that indicate the agent self-reports a hard
# failure on a `done` call. Loop downgrades the run to "failed" so eval
# scoring and SSE consumers don't treat blocked / captcha runs as passes.
_SELF_FAILURE_STATUSES: frozenset[str] = frozenset(
    {"failed", "unable_to_complete", "blocked", "captcha"}
)
# F21: soft-failure status tokens — agent self-reports the run did not fully
# succeed but is not a hard block. Loop downgrades the run to "unverified" so
# the SSE terminal status doesn't claim plain `done` while the result message
# admits "could not access ...".
_SELF_SOFT_FAILURE_STATUSES: frozenset[str] = frozenset({"partial", "incomplete"})
_OFF_PLAN_SENTINEL: str = "off-plan"

# T1: words in a `next_goal` that signal the agent still has work to do
# (browse / interact) rather than report a final answer. Matched as
# whole-word, case-insensitive substrings.
_NEXT_GOAL_NAV_VERBS: tuple[str, ...] = (
    "search",
    "navigate",
    "go to",
    "click",
    "find",
    "look up",
    "look for",
    "fill in",
    "fill out",
    "enter",
    "type",
    "browse",
    "open",
    "submit",
    "load",
    "scroll",
)


def _next_goal_is_navigation(next_goal: Any) -> bool:
    if not isinstance(next_goal, str):
        return False
    lowered = next_goal.lower()
    return any(verb in lowered for verb in _NEXT_GOAL_NAV_VERBS)


_F9_MIN_LEAF_LEN = 4


def _result_leaf_strings(payload: Any) -> list[str]:
    """Yield non-trivial leaf strings from a freeform `done.result` payload.
    Used by F9 to ground the agent's proposed answer against page content."""
    out: list[str] = []

    def _walk(node: Any) -> None:
        if isinstance(node, str):
            if len(node.strip()) >= _F9_MIN_LEAF_LEN:
                out.append(node.strip())
        elif isinstance(node, dict):
            for v in node.values():
                _walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                _walk(v)

    _walk(payload)
    return out


def _result_grounded_in_read(result: Any, latest_read: str) -> bool:
    """F9: True iff any non-trivial leaf string from `result` is a substring
    of `latest_read` (case-insensitive). Empty `latest_read` ⇒ False so the
    pre-existing premature_done gates are unchanged when no read has happened."""
    if not latest_read:
        return False
    haystack = latest_read.lower()
    for leaf in _result_leaf_strings(result):
        if leaf.lower() in haystack:
            return True
    return False


# F20: detect comparison-superlative tasks where the agent commits `done` to a
# single candidate while prior `read` content listed multiple candidates with
# the same numeric field shape (rating, price, review count). Page-shape +
# task-shape signal — no domain vocabulary, no per-site recipes.
_SUPERLATIVE_TOKENS: frozenset[str] = frozenset(
    {
        "best",
        "cheapest",
        "highest",
        "lowest",
        "most",
        "fewest",
        "largest",
        "smallest",
        "biggest",
        "tallest",
        "longest",
        "shortest",
        "fastest",
        "slowest",
        "nearest",
        "closest",
        "farthest",
        "top",
        "oldest",
        "newest",
        "latest",
    }
)
_RATING_RX = re.compile(r"\b[1-5]\.\d\b")
_PRICE_RX = re.compile(r"(?:NT\$|HK\$|S\$|US\$|\$|€|£|¥)\s*\d[\d,]*(?:\.\d+)?")
_COUNT_RX = re.compile(r"\b\d[\d,]*\s+reviews?\b", re.IGNORECASE)


def _task_has_superlative(task: str) -> bool:
    tokens = re.findall(r"\b[a-z]+\b", task.lower())
    return any(t in _SUPERLATIVE_TOKENS for t in tokens)


def _detect_unsupported_superlative(task: str, observation_tape: str, result: Any) -> str | None:
    """Returns a reason string if F20 fires, else None.

    Triggers when:
      1. `task` contains a comparison superlative (whole-word).
      2. `observation_tape` (cumulative read content) has ≥2 distinct values
         of some candidate-shaped numeric field (rating / price / review count).
      3. The stringified `result` references ≤1 distinct value of that same
         field — i.e. the agent committed to one candidate without surfacing
         the comparison.
    """
    if not _task_has_superlative(task):
        return None
    if not observation_tape:
        return None
    result_str = json.dumps(result, ensure_ascii=False) if result is not None else ""
    for label, rx in (("rating", _RATING_RX), ("price", _PRICE_RX), ("review_count", _COUNT_RX)):
        tape_values = set(rx.findall(observation_tape))
        if len(tape_values) < 2:
            continue
        result_values = set(rx.findall(result_str))
        if len(result_values) <= 1:
            return (
                f"task uses a comparison superlative; observed ≥2 candidates "
                f"with {label}-shape values but `done` references only "
                f"{len(result_values)}"
            )
    return None


_ELIDED_AX_TREE_MARKER = "[elided — see latest observation]"
_KEEP_RECENT_AX_TREES = 2


def _build_run_context(locale: str | None, max_steps: int) -> plan_module.RunContext:
    """Assemble the trusted RunContext shown to the planner.

    Date and timezone come from the system clock (via AGENT_TZ env override
    when set). Locale comes from the caller — the frontend supplies it from
    navigator.language so plans are interpreted under the user's region.
    """
    tz_name = os.environ.get("AGENT_TZ")
    if tz_name:
        try:
            from zoneinfo import ZoneInfo

            tz = ZoneInfo(tz_name)
            now = datetime.now(tz)
        except Exception:  # noqa: BLE001
            now = datetime.now().astimezone()
            tz_name = str(now.tzinfo)
    else:
        now = datetime.now().astimezone()
        tz_name = str(now.tzinfo)
    return plan_module.RunContext(
        date=now.date().isoformat(),
        timezone=tz_name,
        locale=locale or os.environ.get("AGENT_LOCALE", "en-US"),
        step_budget=max_steps,
    )


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


_VERIFY_DONE_SYSTEM_PROMPT = (
    "[VERIFY DONE]\n"
    "You verify whether a browser agent's claimed result is grounded in what "
    "it actually observed. Default to unsupported when key result fields "
    "(numbers, dates, named entities like prices, addresses, proper "
    "names) are not present in the observation tape. Also return "
    "unsupported when the agent has not executed an action whose effect "
    "would produce the claimed result — e.g. the result claims a search "
    "result, ranking, or post-filter content, but no click/type/select "
    "action visible earlier could have produced it; a `goto` alone does "
    "not trigger a search. Return supported only when the key fields are "
    "verbatim present in the tape AND any triggering action is visible. "
    "Contradictions (a price/name/date paired with a different value in "
    "the observations) are unsupported as well. Reply ONLY with a single "
    'JSON object: {"verdict": "supported" | "unsupported", '
    '"reason": "<one short sentence>"}.'
)


def _build_observation_tape(messages: list[dict]) -> str:
    """Concatenate read-tool outputs only.

    State messages are dropped: they carry repeated plan progress and AX-tree
    summaries that crowd out the actual evidence within the tape's char budget.
    """
    parts: list[str] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if not isinstance(content, str):
            continue
        if role == "tool" and not content.startswith("Error:"):
            parts.append(content)
    return "\n".join(parts)


_TAPE_NORMALIZE_RE = re.compile(r"\s+")


def _normalize_for_match(s: str) -> str:
    return _TAPE_NORMALIZE_RE.sub(" ", s).strip().lower()


def _iter_string_leaves(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        if value.strip():
            yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _iter_string_leaves(v)
    elif isinstance(value, list | tuple):
        for v in value:
            yield from _iter_string_leaves(v)


_INTERACTION_TOOLS: frozenset[str] = frozenset({"click", "type", "select"})

# T2: numeric leaves (price, ISO/slash dates, comma-thousands, decimals) are
# the highest-risk hallucination targets — they are easy to invent and easy
# to surface as landing-page chrome (teaser cards). Match conservatively:
# require a currency prefix, a thousand-separator, a 2-decimal price form,
# or a date pattern. Plain integers like "42" are NOT numeric-flagged.
_NUMERIC_LEAF_RE = re.compile(
    r"(?:\$|NT\$|US\$|HK\$|JP¥|€|£|¥)\s?\d"  # currency-prefixed
    r"|\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b"  # thousand-separated
    r"|\b\d+\.\d{2}\b"  # 2-decimal (price-like)
    r"|\b\d{4}-\d{2}-\d{2}\b"  # ISO date
    r"|\b\d{1,4}/\d{1,2}/\d{1,4}\b"  # slash date
)
_SHORT_LEAF_THRESHOLD = 6
_SHORT_LEAF_WINDOW_CHARS = 200


def _classify_tool_outputs(messages: list[dict]) -> list[tuple[str | None, str]]:
    """Walk messages and return (tool_name, content) for each non-error tool result.

    Tool name is recovered from the assistant message that emitted the
    matching tool_call_id. Returns in message order.
    """
    name_by_id: dict[str, str] = {}
    for m in messages:
        if m.get("role") != "assistant":
            continue
        for tc in m.get("tool_calls") or []:
            tc_id = tc.get("id")
            fn_name = ((tc.get("function") or {}).get("name")) or None
            if isinstance(tc_id, str) and isinstance(fn_name, str):
                name_by_id[tc_id] = fn_name
    out: list[tuple[str | None, str]] = []
    for m in messages:
        if m.get("role") != "tool":
            continue
        content = m.get("content")
        if not isinstance(content, str) or content.startswith("Error:"):
            continue
        out.append((name_by_id.get(m.get("tool_call_id", "")), content))
    return out


def _post_interaction_tape(messages: list[dict]) -> str:
    """Concatenated tool outputs that came strictly AFTER the most recent
    click/type/select tool call. Empty string when no interaction happened."""
    classified = _classify_tool_outputs(messages)
    last_idx = -1
    for i, (name, _) in enumerate(classified):
        if name in _INTERACTION_TOOLS:
            last_idx = i
    if last_idx == -1:
        return ""
    return "\n".join(c for _, c in classified[last_idx + 1 :])


def _is_numeric_leaf(leaf: str) -> bool:
    return bool(_NUMERIC_LEAF_RE.search(leaf))


def _short_leaves_cluster_with_long(
    short_norms: list[str], long_norms: list[str], norm_tape: str
) -> bool:
    """Each short leaf must appear within ±_SHORT_LEAF_WINDOW_CHARS of at
    least one long leaf in the (normalised) tape."""
    for n_short in short_norms:
        clustered = False
        for n_long in long_norms:
            if not n_long:
                continue
            idx = norm_tape.find(n_long)
            if idx == -1:
                continue
            start = max(0, idx - _SHORT_LEAF_WINDOW_CHARS)
            end = min(len(norm_tape), idx + len(n_long) + _SHORT_LEAF_WINDOW_CHARS)
            if n_short in norm_tape[start:end]:
                clustered = True
                break
        if not clustered:
            return False
    return True


def _result_grounded_in_tape(result: Any, source: str | list[dict]) -> bool:
    """Strict lexical short-circuit for the verifier.

    `source` accepts either a plain tape string (legacy call sites) or the
    full message list (new call sites — enables interaction-recency gating).

    Rules:
    - Every result string leaf must appear (case/whitespace-normalised) in
      the full tape.
    - If any leaf is numeric (price/date), it must additionally appear in
      the tape segment that comes AFTER the most recent click/type/select
      interaction. No interaction → numeric leaves cannot ground.
    - Short leaves (<6 chars) must co-occur with at least one longer leaf
      within a 200-char window — anchors the cluster to a real subject.
    - Legacy string-tape callers skip the interaction gate (no message
      context), preserving existing behaviour.
    """
    if isinstance(source, str):
        full_tape = source
        post_tape: str | None = None  # legacy path: skip interaction gate
    else:
        full_tape = _build_observation_tape(source)
        post_tape = _post_interaction_tape(source)
    norm_full = _normalize_for_match(full_tape)
    if not norm_full:
        return False
    leaves = list(_iter_string_leaves(result))
    if not leaves:
        return False

    if post_tape is not None:
        norm_post = _normalize_for_match(post_tape)
        for leaf in leaves:
            if _is_numeric_leaf(leaf):
                norm_leaf = _normalize_for_match(leaf)
                if not norm_leaf:
                    continue
                if not norm_post or norm_leaf not in norm_post:
                    return False

    norm_pairs = [(leaf, _normalize_for_match(leaf)) for leaf in leaves]
    short_norms = [n for _, n in norm_pairs if 0 < len(n) < _SHORT_LEAF_THRESHOLD]
    long_norms = [n for _, n in norm_pairs if len(n) >= _SHORT_LEAF_THRESHOLD]
    if (
        short_norms
        and long_norms
        and not _short_leaves_cluster_with_long(short_norms, long_norms, norm_full)
    ):
        return False

    for _, norm_leaf in norm_pairs:
        if norm_leaf and norm_leaf not in norm_full:
            return False
    return True


def verify_done_with_llm(
    *,
    task: str,
    result: Any,
    evidence: Any,
    llm_client: LLMClient,
    observation_tape: str | None = None,
    messages: list[dict] | None = None,
) -> tuple[Literal["supported", "unsupported"], str, Any]:
    if messages is not None:
        full_tape = _build_observation_tape(messages)
        ground_source: str | list[dict] = messages
    else:
        full_tape = observation_tape or ""
        ground_source = full_tape
    if _result_grounded_in_tape(result, ground_source):
        return "supported", "every result string appears in the observation tape", None
    user_msg = (
        f"Task: {task}\n\n"
        f"Claimed result:\n{json.dumps(result, ensure_ascii=False)}\n\n"
        f"Claimed evidence:\n{json.dumps(evidence, ensure_ascii=False)}\n\n"
        f"Observations (read outputs during the run):\n"
        f"{full_tape[:8000]}"
    )
    response = llm_client.chat(
        [
            {"role": "system", "content": _VERIFY_DONE_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )
    raw = (response.content or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if "\n" in raw:
            raw = raw.split("\n", 1)[1]
        raw = raw.rstrip("`").strip()
    verdict: Literal["supported", "unsupported"] = "unsupported"
    reason = "verifier returned non-JSON output"
    try:
        parsed = json.loads(raw)
        v = parsed.get("verdict")
        if v in ("supported", "unsupported"):
            verdict = v
            reason = str(parsed.get("reason", ""))
        else:
            reason = f"verifier returned invalid verdict: {v!r}"
    except (ValueError, TypeError):
        pass
    return verdict, reason, response


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
        "Call `done` once the answer is grounded in observed page content. "
        "Do not call `done` before any `read` has surfaced an answer; a `goto` "
        "alone is not grounding. "
        "Step budget: you have at most 20 steps; partial or best-inference "
        "answers are acceptable as long as they are grounded in something "
        "you have read. "
        "When a `click` or `type` fails, retry with a refined `intent` or replan "
        "(try a different selector, scroll, or take a different navigation path). "
        "If two consecutive interactions on the same page produce no URL "
        "change and no new content, try a different navigation path — a "
        "different selector, a fresh search with refined keywords, or a "
        "different URL. "
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
        "When you call `done` you MUST fill three self-eval fields: "
        "`evaluation_previous_action` (one of success/partial/failed/no_action_yet "
        "describing the most recent action), `evaluation_reason` (one sentence "
        "grounded in observed page changes), and `next_goal` (a reporting phrase "
        "like 'report the final answer'). If you would write a navigation/search "
        "verb in `next_goal` (search, navigate, click, find, look up, fill in), "
        "you are not done yet — execute that action first. If `evaluation_"
        "previous_action` would honestly be 'no_action_yet' (you have only "
        "navigated, not interacted), do not call `done` — interact first. "
        "Every action call (`goto`, `click`, `type`, `read`) MUST set "
        "`plan_cursor` to the 1-based plan-step index it advances. If no "
        "current plan step matches what you're about to do, set "
        'plan_cursor="off-plan" with a brief plan_cursor_reason. Two '
        "consecutive off-plan declarations will force a replan, so prefer "
        "to align with the plan when possible. "
    )
    if expect and expect.get("schema"):
        schema = expect["schema"]
        keys = ", ".join(sorted(schema.keys()))
        base += (
            f"\n\nYour `done.result` MUST be a JSON object matching this schema: "
            f"{json.dumps(schema)}. Required fields: {keys}."
        )
    return base


def _body_text(page: Page | None, *, limit: int | None = _BODY_TEXT_LIMIT) -> str:
    """Return the page body text. With limit=None, returns the full innerText
    (used by `read find` so the substring search can scan the whole page).
    With a limit, truncates to that many chars (default path for plain
    `read` and intent-based reads, which can't afford a 50 KB observation).
    """
    if page is None:
        return ""
    text = page.evaluate(_BODY_TEXT_JS)
    if limit is None:
        return text
    return text[:limit]


def _window_around(text: str, query: str, *, window: int = _BODY_TEXT_LIMIT) -> str | None:
    idx = text.lower().find(query.lower())
    if idx == -1:
        return None
    if len(text) <= window:
        return text
    half = window // 2
    start = max(0, idx - half)
    end = min(len(text), start + window)
    start = max(0, end - window)
    return text[start:end]


_LADDER_OUTCOME_MAP: dict[str, Literal["hit", "miss", "ambiguous", "error"]] = {
    "hit": "hit",
    "zero_matches": "miss",
    "ambiguous": "ambiguous",
    "vision_miss": "miss",
}


def _make_ladder_event_handler(
    *,
    intent: str,
    supervisor: Supervisor,
    trace_writer: TraceWriter | None,
    run_id: str | None,
    step_id: str | None,
) -> Callable[[dict], None]:
    """Translate canonical-ladder on_event payloads into LocateEvent / SupervisorEvent.

    Also enforces the supervisor's max_attempts cap at L1_ax — when the
    supervisor decides to halt (after `max_attempts` strikes), this raises
    the original LocatorMiss to abort the ladder before it falls through to
    L2/L3/L4. Without this gate the canonical ladder would happily burn an
    L4_vision call on every repeat-miss intent.
    """

    def handler(payload: dict) -> None:
        tier = payload.get("tier")
        raw_outcome = payload.get("outcome")
        chosen = payload.get("chosen")
        cache_action = payload.get("cache_action")
        miss: LocatorMiss | None = payload.get("miss")

        # Map raw payload outcome to LocateEvent outcome literal.
        if raw_outcome == "cache_write":
            event_outcome: Literal["hit", "miss", "ambiguous", "error"] = "hit"
            cache_action = "write"
        else:
            event_outcome = _LADDER_OUTCOME_MAP.get(str(raw_outcome), "error")

        seq = _emit_locate_event(
            trace_writer=trace_writer,
            run_id=run_id,
            intent=intent,
            tier=tier,  # type: ignore[arg-type]
            outcome=event_outcome,
            cache_action=cache_action,  # type: ignore[arg-type]
            chosen=chosen,
            step_id=step_id,
        )

        if tier == "L1_ax" and miss is not None and event_outcome in ("miss", "ambiguous"):
            decision = supervisor.handle(miss, current_tier="L1_ax")
            if seq is not None:
                _emit_supervisor_event(
                    trace_writer=trace_writer,
                    run_id=run_id,
                    decision=decision,
                    miss=miss,
                    trigger_event_seq=seq,
                    step_id=step_id,
                )
            if decision.next_tier is None:
                raise miss

    return handler


def _emit_locate_event(
    *,
    trace_writer: TraceWriter | None,
    run_id: str | None,
    intent: str,
    tier: Literal["cache", "L1_ax", "L2_dom", "L_textmatch", "L3_rerank", "L4_vision"],
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


_STEP_ADVANCE_CONTENT_MAX = 256


def _emit_step_advance(
    *,
    trace_writer: TraceWriter | None,
    run_id: str | None,
    reason: Literal["no_tool_call", "parse_error", "arg_validate_error"],
    content: str,
    step_id: str | None,
    tool_call_id: str | None = None,
) -> int | None:
    if trace_writer is None or run_id is None:
        return None
    seq = trace_writer.next_seq(run_id)
    truncated = content[:_STEP_ADVANCE_CONTENT_MAX]
    event = StepAdvanceEvent(
        run_id=run_id,
        seq=seq,
        ts=datetime.now(UTC).isoformat(),
        step_id=step_id,
        reason=reason,
        content=truncated,
        tool_call_id=tool_call_id,
    )
    trace_writer.append_event(event)
    return seq


def _emit_act_event(
    *,
    trace_writer: TraceWriter | None,
    run_id: str | None,
    tool: str,
    args: dict[str, Any],
    outcome: Literal["ok", "no_effect", "nav", "timeout", "error", "halted_by_supervisor"],
    ms: int,
    step_id: str | None = None,
    diff: dict[str, Any] | None = None,
) -> int:
    if trace_writer is None or run_id is None:
        return 0
    seq = trace_writer.next_seq(run_id)
    event = ActEvent(
        run_id=run_id,
        seq=seq,
        ts=datetime.now(UTC).isoformat(),
        step_id=step_id,
        tool=tool,
        args=args,
        outcome=outcome,
        diff=diff if diff is not None else {},
        ms=ms,
    )
    trace_writer.append_event(event)
    return seq


def _locate_with_supervisor(
    page: Page,
    intent: str,
    supervisor: Supervisor,
    *,
    cache: LocatorCache | None = None,
    trace_writer: TraceWriter | None = None,
    run_id: str | None = None,
    step_id: str | None = None,
    llm_chat: Callable[..., Any] | None = None,
) -> LocateResult:
    from agent.locate import locate as canonical_locate

    handler = _make_ladder_event_handler(
        intent=intent,
        supervisor=supervisor,
        trace_writer=trace_writer,
        run_id=run_id,
        step_id=step_id,
    )
    return canonical_locate(
        page,
        intent,
        llm_chat=llm_chat,
        cache=cache,
        on_event=handler,
    )


def _locate_or_error_msg(
    page: Page,
    intent: str,
    supervisor: Supervisor,
    *,
    cache: LocatorCache | None,
    trace_writer: TraceWriter | None,
    run_id: str | None,
    step_id: str | None,
    llm_chat: Callable[..., Any] | None = None,
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
            llm_chat=llm_chat,
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
    llm_chat: Callable[..., Any] | None = None,
) -> str:
    if tool_name == "goto":
        url = args.get("url")
        if not isinstance(url, str) or not url:
            # F29: emit an act event so the trace records why this step
            # produced no navigation (otherwise step_id increments silently).
            _emit_act_event(
                trace_writer=trace_writer,
                run_id=run_id,
                tool="goto",
                args={"url": url} if url is not None else {},
                outcome="error",
                ms=0,
                step_id=step_id,
            )
            return "Error: goto requires a non-empty 'url' string argument"
        from agent.browser import NavigationError

        t_goto = time.monotonic()
        try:
            browser.goto(url)
        except NavigationError as e:
            _emit_act_event(
                trace_writer=trace_writer,
                run_id=run_id,
                tool="goto",
                args={"url": url},
                outcome="error",
                ms=int((time.monotonic() - t_goto) * 1000),
                step_id=step_id,
            )
            return f"Error: navigation failed for {url}: {e}"
        _emit_act_event(
            trace_writer=trace_writer,
            run_id=run_id,
            tool="goto",
            args={"url": url},
            outcome="ok",
            ms=int((time.monotonic() - t_goto) * 1000),
            step_id=step_id,
        )
        return f"Navigated to {url}"
    if tool_name == "read":
        intent: str | None = args.get("intent")
        find: str | None = args.get("find")
        page = browser._page
        t_read = time.monotonic()

        def _emit_read(outcome: Literal["ok", "error"], read_args: dict) -> None:
            _emit_act_event(
                trace_writer=trace_writer,
                run_id=run_id,
                tool="read",
                args=read_args,
                outcome=outcome,
                ms=int((time.monotonic() - t_read) * 1000),
                step_id=step_id,
            )

        if intent and find:
            _emit_read("error", {"intent": intent, "find": find})
            return "Error: read accepts either 'intent' or 'find', not both"
        if find is not None:
            if not isinstance(find, str) or not find.strip():
                _emit_read("error", {"find": find})
                return "Error: read 'find' must be a non-empty string"
            # F23: scan the FULL page text, not the 2 KB-truncated body.
            # Truncation moves to *after* the match (window slice) so a
            # substring past the default window is still findable.
            try:
                full = _body_text(page, limit=None)
            except Exception as e:  # real page failure (closed page, evaluate threw)
                _emit_read("error", {"find": find})
                return f"Error: page evaluate failed for find={find!r}: {e}"
            window = _window_around(full, find)
            if window is None:
                # F23: a missing substring is not a page failure — surface as
                # an `ok` outcome with match_count=0 so the agent reads it as
                # "look elsewhere on this page" rather than "page is broken".
                _emit_read("ok", {"find": find, "match_count": 0})
                return (
                    f"no match for {find!r} in page text (scanned {len(full)} chars; match_count=0)"
                )
            _emit_read("ok", {"find": find, "match_count": 1})
            return window
        if intent:
            located = _locate_or_error_msg(
                page,
                intent,
                supervisor,
                cache=locator_cache,
                trace_writer=trace_writer,
                run_id=run_id,
                step_id=step_id,
                llm_chat=llm_chat,
            )
            if isinstance(located, str):
                # F12: fall back to a full-body read instead of returning an
                # error. Round-4 U1/U4 traces showed the LLM consistently
                # recovering from `read intent` errors by issuing a
                # `read(find=...)` or no-args `read()` on the next turn —
                # auto-doing the fallback saves one LLM round-trip.
                _emit_read("ok", {"intent": intent, "fallback": "body"})
                return _body_text(page)
            from agent.browser import ElementNotFound

            try:
                result = browser.read(located.selector)
            except ElementNotFound:
                # Same F12 rationale: vanished element ⇒ body read fallback.
                _emit_read("ok", {"intent": intent, "fallback": "body"})
                return _body_text(page)
            _emit_read("ok", {"intent": intent})
            return result
        body = _body_text(page)
        _emit_read("ok", {})
        return body
    if tool_name == "click":
        intent_val: str | None = args.get("intent")
        if not isinstance(intent_val, str) or not intent_val:
            # F29: every dispatch path emits something so step_ids stay contiguous.
            _emit_act_event(
                trace_writer=trace_writer,
                run_id=run_id,
                tool="click",
                args={"intent": intent_val} if intent_val is not None else {},
                outcome="error",
                ms=0,
                step_id=step_id,
            )
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
            llm_chat=llm_chat,
        )
        if isinstance(located, str):
            # F29: a locate-failed click is the most common trace gap source —
            # emit an act so reviewers see why this step performed no click.
            _emit_act_event(
                trace_writer=trace_writer,
                run_id=run_id,
                tool="click",
                args={"intent": intent_val},
                outcome="error",
                ms=0,
                step_id=step_id,
            )
            return located
        locate_result = located
        url_before = page.url
        t_click = time.monotonic()
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        outcome: Literal["ok", "no_effect", "nav", "timeout", "error"]
        diff: dict[str, Any] = {}
        try:
            page.locator(locate_result.selector).click(timeout=5000)
        except PlaywrightTimeoutError:
            # F17: a click that times out usually means a paint-blocking
            # overlay (cookie banner, modal, age gate) is intercepting
            # pointer events. Retry once via JS dispatch — bypasses the
            # hit-test entirely without resorting to site-specific
            # banner-dismissal heuristics.
            try:
                page.locator(locate_result.selector).evaluate("(el) => el.click()")
            except PlaywrightError:
                outcome = "timeout"
            else:
                try:
                    page.wait_for_load_state("load", timeout=3000)
                except PlaywrightTimeoutError:
                    pass
                outcome = "nav" if page.url != url_before else "ok"
                diff = {"retry": "js_click"}
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
            diff=diff,
        )
        if outcome in _CLICK_SUCCESS_OUTCOMES:
            return f"Clicked {intent_val!r} ({outcome})"
        return f"Error: click {outcome} for intent {intent_val!r}"
    if tool_name == "type":
        intent_val = args.get("intent")
        text_val = args.get("text")
        submit_val = bool(args.get("submit", False))
        if not isinstance(intent_val, str) or not intent_val:
            # F29: contiguous step_ids — emit an error act for missing intent.
            _emit_act_event(
                trace_writer=trace_writer,
                run_id=run_id,
                tool="type",
                args={
                    k: v
                    for k, v in {"intent": intent_val, "text": text_val}.items()
                    if v is not None
                },
                outcome="error",
                ms=0,
                step_id=step_id,
            )
            return "Error: type requires a non-empty 'intent' string argument"
        if not isinstance(text_val, str) or not text_val:
            # F29: contiguous step_ids — emit an error act for missing text.
            _emit_act_event(
                trace_writer=trace_writer,
                run_id=run_id,
                tool="type",
                args={
                    k: v
                    for k, v in {"intent": intent_val, "text": text_val}.items()
                    if v is not None
                },
                outcome="error",
                ms=0,
                step_id=step_id,
            )
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
            llm_chat=llm_chat,
        )
        if isinstance(located, str):
            # F29: locate-failed type is the symmetric gap to F29's click case.
            _emit_act_event(
                trace_writer=trace_writer,
                run_id=run_id,
                tool="type",
                args={"intent": intent_val, "text": text_val},
                outcome="error",
                ms=0,
                step_id=step_id,
            )
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
    # F29: unknown-tool dispatch should still leave a trace record.
    _emit_act_event(
        trace_writer=trace_writer,
        run_id=run_id,
        tool=tool_name,
        args=args,
        outcome="error",
        ms=0,
        step_id=step_id,
    )
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
    locale: str | None = None,
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
    _consecutive_off_plan_steps: int = 0
    _max_plan_cursor_seen: int = 0  # F2: highest 1-based plan_cursor advanced this run
    # F7: rolling window of action outcomes ("ok" / "error") for the most
    # recent goto/click/type/read calls. Used to reject `done` after
    # consecutive failures.
    _recent_outcomes: list[str] = []
    # F9: most recent successful read tool result (body / window / element
    # text). Used to ground a `done` result against actual page content
    # before classifying it as premature.
    _latest_read_content: str = ""
    # F6: per-(tool, classification) halt counter; circuit-breaker fires
    # after _CIRCUIT_BREAKER_THRESHOLD halts on the same key.
    _halt_counts: dict[tuple[str, str], int] = {}
    _CIRCUIT_BREAKER_THRESHOLD = 3
    _force_done_next: bool = False
    _no_progress_warned: bool = False
    _prev_observation: dict | None = None
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
        step_saw_on_plan: bool = False
        step_saw_off_plan: bool = False
        step_off_plan_reason: str | None = None

        observation = observe.build_observation(browser, last_actions)
        # T5: digest is kept as a step-local; we do NOT stash it on
        # `observation` because that would leak into trace events and the
        # state JSON sent to the LLM (which would also break replay-fixture
        # round-trips).
        if isinstance(observation, dict):
            dom_digest_value = observe.compute_dom_digest(_prev_observation, observation)
            _prev_observation = observation
        else:
            dom_digest_value = ""
        last_actions = []

        if step_num == 1:
            run_context = _build_run_context(locale, max_steps)
            _emit_plan_event(
                events,
                "started",
                ["Planning..."],
                str(uuid.uuid4()),
                trace_writer=trace_writer,
                run_id=run_id,
                step_id=_step_id,
            )

            def _traced_ask_user(
                question: str,
                _events=events,
                _writer=trace_writer,
                _run_id=run_id,
                _step_id=_step_id,
                _cb=ask_user_callback,
            ) -> str:
                _emit_plan_event(
                    _events,
                    "ask_user",
                    [f"Asking user: {question}"],
                    str(uuid.uuid4()),
                    trace_writer=_writer,
                    run_id=_run_id,
                    step_id=_step_id,
                )
                return "" if _cb is None else _cb(question)

            active_plan, plan_resp = plan_module.plan(
                task,
                observation,
                llm_client,
                ask_user_callback=_traced_ask_user if ask_user_callback is not None else None,
                context=run_context,
            )
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
        # Skip the digest prefix when nothing changed — "unchanged" is
        # already implied by repeated ax_fingerprint and just costs tokens.
        if dom_digest_value and dom_digest_value != "unchanged":
            digest_prefix = f"DOM change since last step: {dom_digest_value}\n\n"
        else:
            digest_prefix = ""
        state_payload = json.dumps(observation)
        messages.append(
            {
                "role": "user",
                "content": (
                    f"{budget_prefix}{plan_prefix}{digest_prefix}"
                    f"{STATE_MESSAGE_PREFIX}{state_payload}"
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
            _emit_step_advance(
                trace_writer=trace_writer,
                run_id=run_id,
                reason="no_tool_call",
                content=response.content or "",
                step_id=_step_id,
            )
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
                _emit_step_advance(
                    trace_writer=trace_writer,
                    run_id=run_id,
                    reason="parse_error",
                    content=tool_call.arguments or "",
                    step_id=_step_id,
                    tool_call_id=tool_call.id,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": f"Error: invalid JSON arguments ({exc.msg})",
                    }
                )
                continue

            if not isinstance(args, dict):
                _emit_step_advance(
                    trace_writer=trace_writer,
                    run_id=run_id,
                    reason="arg_validate_error",
                    content=tool_call.arguments or "",
                    step_id=_step_id,
                    tool_call_id=tool_call.id,
                )
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

            if tool_call.name in _PLAN_CURSOR_TOOLS:
                cursor = args.get("plan_cursor")
                if isinstance(cursor, int) and cursor >= 1:
                    step_saw_on_plan = True
                    if cursor > _max_plan_cursor_seen:
                        _max_plan_cursor_seen = cursor
                elif cursor == _OFF_PLAN_SENTINEL:
                    step_saw_off_plan = True
                    if step_off_plan_reason is None:
                        reason = args.get("plan_cursor_reason")
                        if isinstance(reason, str) and reason:
                            step_off_plan_reason = reason

            if tool_call.name == "done":
                # I4: when the agent's `done` payload self-reports a known
                # failure / soft-failure status, trust that admission and
                # bypass the premature_done halt and superlative-mismatch
                # replan. Otherwise F10 fires "do more work" and the loop
                # keeps iterating (A1 round-10: F10 halted, the LLM emitted
                # another click in the next step, and the run leaked past
                # what should have been a terminal `done`). F5/F21 below
                # handle the actual status downgrade to failed/unverified.
                _self_failure_admitted = False
                _result_payload_for_status = args.get("result")
                if isinstance(_result_payload_for_status, dict):
                    _self_status = _result_payload_for_status.get("status")
                    if isinstance(_self_status, str):
                        _normalized = _self_status.lower()
                        _self_failure_admitted = (
                            _normalized in _SELF_FAILURE_STATUSES
                            or _normalized in _SELF_SOFT_FAILURE_STATUSES
                        )
                # T1 self-eval gate: reject `done` when the agent's own
                # evaluation_previous_action / next_goal indicate it has not
                # actually done the work yet. This catches the goto→done
                # hallucination mode where the agent fabricates results
                # without executing the planned interactions.
                eval_prev = args.get("evaluation_previous_action")
                next_goal = args.get("next_goal")
                premature_reason: str | None = None
                # F18: precondition — when no `read` has ever succeeded in
                # this run AND the proposed result carries a non-trivial
                # answer, refuse the done. Otherwise the agent is reporting
                # content it never read (round-5 A3: cheapest_fare lifted
                # from a homepage promo banner with no intervening read).
                # An empty/trivial result still flows through to the regular
                # heuristics so navigation-only tasks aren't blocked.
                if eval_prev == "no_action_yet" and step_num <= 1:
                    premature_reason = (
                        "agent declared evaluation_previous_action="
                        "'no_action_yet' at step 1 — no interaction has "
                        "occurred yet, so a final answer cannot be grounded"
                    )
                elif _next_goal_is_navigation(next_goal):
                    premature_reason = (
                        f"next_goal={next_goal!r} names a navigation/search "
                        "verb — that is more work to do, not a final answer"
                    )
                elif (
                    len(_recent_outcomes) >= 2
                    and _recent_outcomes[-1] != "ok"
                    and _recent_outcomes[-2] != "ok"
                ):
                    # F7: don't accept `done` after two consecutive action
                    # failures — the page state has not changed since the
                    # last successful action and any answer would be
                    # fabricated. Forces the agent to either change tool /
                    # intent, or call `fail` cleanly.
                    premature_reason = (
                        "the last 2 actions failed (timeout/error); the "
                        "page state has not advanced — switch tool or "
                        "intent, or call `fail`, instead of `done`"
                    )
                else:
                    # F2: reject `done` when the agent USED plan_cursor (set it
                    # at least once) but never advanced past the first half of
                    # a multi-step plan. Only applies to plans with >=3 steps;
                    # short plans trip too easily. Guard with `>= 1` so runs
                    # where the LLM omits plan_cursor entirely fall through
                    # to other heuristics rather than getting blocked.
                    plan_len = len(active_plan.steps) if active_plan is not None else 0
                    if (
                        plan_len >= 3
                        and _max_plan_cursor_seen >= 1
                        and _max_plan_cursor_seen * 2 < plan_len
                    ):
                        premature_reason = (
                            f"plan_cursor only reached {_max_plan_cursor_seen} of "
                            f"{plan_len} plan steps — execute the remaining steps "
                            "(fill forms, click search, read results) before `done`"
                        )
                if premature_reason is not None and _result_grounded_in_read(
                    args.get("result"), _latest_read_content
                ):
                    # F9: the proposed result has substring evidence in the
                    # most recent read content. The pre-existing heuristics
                    # (plan_cursor, next_goal verbs, etc.) misclassify this
                    # as premature on extraction tasks where the answer is
                    # already on the page. Downgrade halt → accept.
                    premature_reason = None
                if premature_reason is not None and _self_failure_admitted:
                    # I4: agent has admitted partial/incomplete/failed in
                    # result.status; nagging it via premature_done halt only
                    # leaks more tool calls. Skip to F21 self-status
                    # downgrade below.
                    premature_reason = None
                if premature_reason is not None:
                    use_writer = trace_writer is not None and run_id is not None
                    # F10: emit an `act` event for the rejected `done` so the
                    # trace shows what was proposed. Previously the supervisor
                    # halt fired with trigger_event_seq=0 and there was no
                    # corresponding act event — leaving an unexplained gap in
                    # the trace.
                    act_seq = _emit_act_event(
                        trace_writer=trace_writer,
                        run_id=run_id,
                        tool="done",
                        args=dict(args),
                        outcome="halted_by_supervisor",
                        ms=0,
                        step_id=_step_id,
                    )
                    sup_seq = trace_writer.next_seq(run_id) if use_writer else 0
                    sup_event = SupervisorEvent(
                        run_id=run_id if use_writer else "loop",
                        seq=sup_seq,
                        ts=datetime.now(UTC).isoformat() if use_writer else "",
                        step_id=_step_id,
                        trigger_event_seq=act_seq,
                        classified_as="premature_done",
                        policy="halt",
                        attempt=1,
                    )
                    if use_writer:
                        trace_writer.append_event(sup_event)
                    elif events is not None:
                        events.append(sup_event)
                    # F6: circuit-breaker — repeated halts on the same
                    # (tool, classification) mean the LLM is ignoring the
                    # rejection. After N halts, terminate with `failed`
                    # instead of burning the step budget on retries.
                    halt_key = ("done", "premature_done")
                    _halt_counts[halt_key] = _halt_counts.get(halt_key, 0) + 1
                    if _halt_counts[halt_key] >= _CIRCUIT_BREAKER_THRESHOLD:
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
                            reason=(
                                "circuit-breaker: "
                                f"{_halt_counts[halt_key]} consecutive "
                                f"'premature_done' halts on `done` — "
                                "agent stuck in a rejection loop"
                            ),
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
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": (
                                f"Supervisor: rejected premature `done` ({premature_reason}). "
                                "Execute the missing action (click / type / read), then "
                                "re-evaluate before calling `done` again."
                            ),
                        }
                    )
                    continue

                # F20: list-shape comparison-superlative mismatch — fires
                # before the LLM judge so a structural signal can replan
                # without burning a judge call. Severity sits between
                # tool_error and unsupported_done so the LLM-judge path can
                # still escalate above it.
                _f20_reason = _detect_unsupported_superlative(
                    task,
                    _build_observation_tape(messages),
                    args.get("result"),
                )
                if (
                    _f20_reason is not None
                    and not _self_failure_admitted
                    and supervisor.can_replan("unsupported_superlative")
                ):
                    if trace_writer is not None and run_id is not None:
                        sup_seq = trace_writer.next_seq(run_id)
                        trace_writer.append_event(
                            SupervisorEvent(
                                run_id=run_id,
                                seq=sup_seq,
                                ts=datetime.now(UTC).isoformat(),
                                step_id=_step_id,
                                trigger_event_seq=0,
                                classified_as="unsupported_superlative",
                                policy="replan",
                                attempt=1,
                            )
                        )
                    elif events is not None:
                        events.append(
                            SupervisorEvent(
                                run_id=run_id if run_id else "loop",
                                seq=0,
                                ts="",
                                step_id=_step_id,
                                trigger_event_seq=0,
                                classified_as="unsupported_superlative",
                                policy="replan",
                                attempt=1,
                            )
                        )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": (
                                f"Supervisor: {_f20_reason}. The task asks for a "
                                "comparison; read the list of candidates and "
                                "compare the relevant field across them before "
                                "calling `done` again."
                            ),
                        }
                    )
                    new_plan, replan_resp = plan_module.replan(
                        task,
                        observation,
                        active_plan,
                        f"unsupported superlative: {_f20_reason}",
                        llm_client,
                    )
                    cum_prompt_tokens += replan_resp.usage.prompt_tokens
                    cum_completion_tokens += replan_resp.usage.completion_tokens
                    cum_usd += replan_resp.usd
                    supervisor.record_replan("unsupported_superlative")
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

                evidence = args.get("evidence")
                verifier = _check_evidence(evidence)

                if verifier["ok"]:
                    verdict, reason, judge_resp = verify_done_with_llm(
                        task=task,
                        messages=messages,
                        result=args.get("result"),
                        evidence=evidence,
                        llm_client=llm_client,
                    )
                    if judge_resp is not None:
                        cum_prompt_tokens += judge_resp.usage.prompt_tokens
                        cum_completion_tokens += judge_resp.usage.completion_tokens
                        cum_usd += judge_resp.usd

                    if verdict == "unsupported":
                        verifier = {
                            "ok": False,
                            "reasons": [f"verifier: {reason}"],
                        }
                        if trace_writer is not None and run_id is not None:
                            sup_seq = trace_writer.next_seq(run_id)
                            trace_writer.append_event(
                                SupervisorEvent(
                                    run_id=run_id,
                                    seq=sup_seq,
                                    ts=datetime.now(UTC).isoformat(),
                                    step_id=_step_id,
                                    trigger_event_seq=0,
                                    classified_as="unsupported_done",
                                    policy="replan",
                                    attempt=1,
                                )
                            )
                        if supervisor.can_replan("unsupported_done"):
                            messages.append(
                                {
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": (
                                        "Supervisor: claimed result not supported by "
                                        f"observations ({reason}). Gather missing "
                                        "evidence with `read`/`goto`/`click` and call "
                                        "`done` again, or call `fail` with a rationale."
                                    ),
                                }
                            )
                            new_plan, replan_resp = plan_module.replan(
                                task,
                                observation,
                                active_plan,
                                f"unsupported done: {reason}",
                                llm_client,
                            )
                            cum_prompt_tokens += replan_resp.usage.prompt_tokens
                            cum_completion_tokens += replan_resp.usage.completion_tokens
                            cum_usd += replan_resp.usd
                            supervisor.record_replan("unsupported_done")
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

                status: RunStatus = "succeeded" if verifier["ok"] else "unverified"
                # F5/F21: if the agent's own result payload self-reports a
                # failure status, downgrade the run accordingly. Hard
                # failures (failed/blocked/captcha/unable_to_complete) flip
                # to "failed"; soft failures (partial/incomplete) flip to
                # "unverified" so the SSE terminal status reflects what the
                # agent actually accomplished.
                _result_payload = args.get("result")
                if isinstance(_result_payload, dict):
                    _self_status = _result_payload.get("status")
                    if isinstance(_self_status, str):
                        _normalized = _self_status.lower()
                        if _normalized in _SELF_FAILURE_STATUSES:
                            status = "failed"
                        elif _normalized in _SELF_SOFT_FAILURE_STATUSES:
                            status = "unverified"
                _emit_act_event(
                    trace_writer=trace_writer,
                    run_id=run_id,
                    tool="done",
                    args=args,
                    outcome="ok",
                    ms=0,
                    step_id=_step_id,
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
                _emit_act_event(
                    trace_writer=trace_writer,
                    run_id=run_id,
                    tool="fail",
                    args=args,
                    outcome="ok",
                    ms=0,
                    step_id=_step_id,
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
                llm_chat=llm_client.chat,
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
            # F9: remember the most recent successful read content so a
            # subsequent `done` can be grounded against actual page text.
            if tool_call.name == "read" and not is_error:
                _latest_read_content = tool_result
            # F7: track outcomes of *interaction* actions only (click/type)
            # for the consecutive-failures gate on `done`. `goto` is network /
            # nav and `read` is info-retrieval — failures there are normal
            # ("page didn't have what I asked for") and shouldn't block `done`.
            if tool_call.name in {"click", "type"}:
                _recent_outcomes.append("error" if is_error else "ok")
                if len(_recent_outcomes) > 5:
                    del _recent_outcomes[0]
            # F6: any successful action is "productive intervening work";
            # reset the halt counter so it tracks *consecutive* halts.
            if tool_call.name in {"goto", "click", "type", "read"} and not is_error:
                _halt_counts.clear()
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
                if supervisor.can_replan("tool_error"):
                    new_plan, replan_resp = plan_module.replan(
                        task, observation, active_plan, tool_result, llm_client
                    )
                    cum_prompt_tokens += replan_resp.usage.prompt_tokens
                    cum_completion_tokens += replan_resp.usage.completion_tokens
                    cum_usd += replan_resp.usd
                    supervisor.record_replan("tool_error")
                    active_plan = new_plan
                    _no_progress_buf.clear()
                    # F7: replan supersedes the prior plan; recent click/type
                    # failures were against the old plan's targets, so they
                    # should not block `done` on the new plan.
                    _recent_outcomes.clear()
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

        # On-plan resets the counter; only-off-plan increments it; steps
        # without any cursor (legacy / no plan_cursor) are neutral.
        if step_saw_on_plan:
            _consecutive_off_plan_steps = 0
        elif step_saw_off_plan:
            _consecutive_off_plan_steps += 1
            if (
                not replanned_this_step
                and active_plan is not None
                and _consecutive_off_plan_steps >= _OFF_PLAN_REPLAN_THRESHOLD
                and supervisor.can_replan("off_plan")
            ):
                feedback_reason = (
                    "off-plan: " + step_off_plan_reason
                    if step_off_plan_reason
                    else "off-plan for two consecutive steps"
                )
                new_plan, replan_resp = plan_module.replan(
                    task,
                    observation,
                    active_plan,
                    feedback_reason,
                    llm_client,
                )
                cum_prompt_tokens += replan_resp.usage.prompt_tokens
                cum_completion_tokens += replan_resp.usage.completion_tokens
                cum_usd += replan_resp.usd
                supervisor.record_replan("off_plan")
                active_plan = new_plan
                _no_progress_buf.clear()
                _consecutive_off_plan_steps = 0
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
