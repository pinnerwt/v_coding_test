from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agent.llm import ChatResponse, LLMClient, ToolCall

_PLAN_SYSTEM = (
    "You are a planning assistant for a browser agent. Before planning, "
    "FIRST check whether the task gives you enough information to plan "
    "concrete steps. Information is INSUFFICIENT when, for example: the "
    "task names an entity that plausibly has multiple matches (a brand "
    "with several branches/locations, a person with a common name, a "
    "product with multiple variants) without saying which one; a key "
    "parameter is missing (a date, a quantity, a destination); the task "
    "uses a superlative without a comparator (best, cheapest, nearest, "
    "top, most) and the ranking criterion or a location/category "
    "constraint is not given; or the user's intent could be reasonably "
    "interpreted in more than one way. Information is SUFFICIENT when "
    "the task points to a single unambiguous target with all parameters "
    "present (most simple fact-lookup or navigation tasks fall here). "
    "If information is INSUFFICIENT, call the `ask_user` tool with a "
    "single specific clarifying question, wait for the answer, then "
    "produce the final plan with that answer baked in. Each `ask_user` "
    "call must request exactly one slot — if multiple slots are missing, "
    "ask the most blocking one first, then ask the next after the answer "
    "arrives. Do NOT bundle two questions into one with 'and'. Do NOT "
    "guess the missing information. Do NOT include 'ask the user: ...' "
    "as a plan step — that step happens here, in planning, not during "
    "navigation. If you have already asked the user about a particular "
    "slot once and the answer did not fill it, do NOT ask again — pick "
    "a sane default and proceed, or produce a best-effort plan. "
    "If information is SUFFICIENT, just produce the plan. "
    "Examples of when to ask vs. plan (described by shape, not by topic):\n"
    "  Ambiguous superlative without a comparator (best/cheapest/nearest/"
    "top/most X, with no ranking criterion or location/category bound) — "
    "ask which criterion or constraint to apply before planning.\n"
    "  Superlative WITH a clear comparator (a date, a route, a price "
    "ceiling, a category, or any constraint that fixes the ranking) — "
    "plan directly.\n"
    "  Single unambiguous fact lookup (a named entity with one canonical "
    "answer) — plan directly.\n"
    "When you produce the final plan, respond with ONLY a JSON object: "
    '{"steps": ["step 1", ...], "expected_end_state": "..."} — no tool '
    "call."
)

_REPLAN_SYSTEM = (
    "You are a planning assistant. The prior plan failed partway through. "
    "Given the task, current state, prior steps, and failure reason, "
    "produce a revised short ordered list of steps. "
    'Respond with ONLY a JSON object: {"steps": ["step 1", ...], "expected_end_state": "..."}'
)

_ASK_USER_TOOL = {
    "type": "function",
    "function": {
        "name": "ask_user",
        "description": (
            "Ask the human user a single clarifying question to resolve "
            "ambiguity in the task before planning concrete steps."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "A specific clarifying question.",
                }
            },
            "required": ["question"],
        },
    },
}

_MAX_ASK_USER_ROUNDS = 3
_MIN_PLAN_STEPS = 2
_TOO_SHORT_PLAN_MESSAGE = (
    "Your previous plan had fewer than 2 concrete steps. A plan that "
    "just restates the task is not actionable. Produce a new plan with "
    "at least 2 distinct navigation/interaction steps."
)

# F19: when ask_user supplies an answer, the resulting plan must
# substring-reference at least one non-stopword token from that answer.
# Round-6 A3 trace showed the planner re-stating the raw task verbatim and
# losing the user-supplied date entirely. Generic stopword set, no domain
# vocabulary — this enforces "the answer made it into the plan" without
# encoding any topic preferences.
_ANSWER_STOPWORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "of",
        "in",
        "on",
        "and",
        "or",
        "for",
        "to",
        "at",
        "by",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "with",
        "from",
        "as",
        "it",
        "this",
        "that",
        "these",
        "those",
        "one",
        "two",
        "any",
    }
)
_ANSWER_NOT_INCORPORATED_MESSAGE = (
    "The user's answer must be incorporated into the plan; the plan you "
    "just produced does not reference it. Produce a new plan whose steps "
    "explicitly use the user's answer."
)


def _answer_tokens(answer: str) -> list[str]:
    """Split on whitespace, lowercase, strip non-alphanumeric edges, drop
    stopwords. Returns the enforceable content tokens for the F19 check."""
    raw = answer.lower().split()
    out: list[str] = []
    for tok in raw:
        cleaned = tok.strip(" \t\r\n.?!,;:'\"()[]{}/")
        if not cleaned or cleaned in _ANSWER_STOPWORDS:
            continue
        out.append(cleaned)
    return out


def _plan_references_answer(plan: Plan, answer: str) -> bool:
    """True if at least one non-stopword token from `answer` appears as a
    case-insensitive substring in any plan step or expected_end_state. If
    the answer has no enforceable tokens after stopword removal, returns
    True (no enforcement)."""
    tokens = _answer_tokens(answer)
    if not tokens:
        return True
    haystack = (" ".join(plan.steps) + " " + plan.expected_end_state).lower()
    return any(tok in haystack for tok in tokens)


@dataclass(frozen=True)
class Plan:
    steps: list[str]
    expected_end_state: str


@dataclass(frozen=True)
class RunContext:
    """Trusted execution context surfaced to the planner: when 'now' is, what
    timezone/locale to interpret region-sensitive tasks under, and how many
    navigation steps the loop has to spend.
    """

    date: str
    timezone: str
    locale: str
    step_budget: int


def _format_run_context(ctx: RunContext) -> str:
    return (
        "Run context:\n"
        f"  date: {ctx.date}\n"
        f"  timezone: {ctx.timezone}\n"
        f"  locale: {ctx.locale}\n"
        f"  step_budget: {ctx.step_budget}\n\n"
    )


def _fallback(task: str) -> Plan:
    return Plan(steps=[task], expected_end_state="task complete")


def _strip_code_fence(content: str) -> str:
    """Strip a leading ```[lang]\\n ... \\n``` fence if present."""
    s = content.strip()
    if s.startswith("```"):
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1 :]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()
    return s


def _parse_plan(content: str | None, task: str) -> Plan:
    if not content:
        return _fallback(task)
    try:
        data = json.loads(_strip_code_fence(content))
        steps = data["steps"]
        if not isinstance(steps, list) or not all(isinstance(s, str) for s in steps):
            return _fallback(task)
        end_state = data.get("expected_end_state", "task complete")
        return Plan(steps=steps, expected_end_state=str(end_state))
    except (json.JSONDecodeError, KeyError, TypeError):
        return _fallback(task)


_DEDUP_SYNTHETIC_ANSWER = (
    "(already asked the user about this slot; the answer did not fill it. "
    "Do not call ask_user again — produce a best-effort plan now using "
    "sane defaults for any still-missing fields.)"
)


def _normalize_question(q: str) -> str:
    """Lowercase, collapse whitespace, drop trailing punctuation. Used to
    detect near-duplicate ask_user questions across rounds."""
    return " ".join(q.lower().strip(" \t\r\n.?!,").split())


def _handle_ask_user_tool_call(
    tool_call: ToolCall,
    ask_user_callback: Callable[[str], str] | None,
    asked_fingerprints: set[str],
    received_answers: list[str],
    dedup_emitted: list[bool],
) -> str:
    """Resolve an ask_user tool call into the string content for the tool message.

    Tracks normalized fingerprints of questions already asked in this plan()
    invocation. After the first ask, subsequent ask_user calls receive a
    synthetic answer that tells the LLM to stop re-asking — they do NOT
    invoke ask_user_callback again.
    """
    try:
        args = json.loads(tool_call.arguments) if tool_call.arguments else {}
    except json.JSONDecodeError:
        return "Error: ask_user arguments were not valid JSON."
    question = args.get("question")
    if not isinstance(question, str) or not question.strip():
        return "Error: ask_user requires a non-empty 'question' string."
    if asked_fingerprints:
        dedup_emitted.append(True)
        return _DEDUP_SYNTHETIC_ANSWER
    asked_fingerprints.add(_normalize_question(question))
    if ask_user_callback is None:
        return (
            "Error: ask_user is not available in this run (no callback wired). "
            "Produce a best-effort plan from the task as stated."
        )
    try:
        answer = str(ask_user_callback(question))
    except Exception as exc:  # noqa: BLE001
        return f"Error: ask_user callback raised: {exc}"
    received_answers.append(answer)
    return answer


def plan(
    task: str,
    observation: dict,
    llm: LLMClient,
    *,
    ask_user_callback: Callable[[str], str] | None = None,
    context: RunContext | None = None,
) -> tuple[Plan, ChatResponse]:
    ctx_block = _format_run_context(context) if context is not None else ""
    messages: list[dict] = [
        {"role": "system", "content": _PLAN_SYSTEM},
        {
            "role": "user",
            "content": (f"{ctx_block}Task: {task}\n\nCurrent state: {json.dumps(observation)}"),
        },
    ]
    last_response: Any = None
    asked_fingerprints: set[str] = set()
    received_answers: list[str] = []
    dedup_emitted: list[bool] = []
    short_plan_retried = False
    answer_retry_used = False
    for _ in range(_MAX_ASK_USER_ROUNDS + 1):
        response = llm.chat(messages, tools=[_ASK_USER_TOOL])
        last_response = response
        ask_calls = [tc for tc in (response.tool_calls or []) if tc.name == "ask_user"]
        if not ask_calls:
            parsed = _parse_plan(response.content, task)
            # F11: a 1-step plan that just restates the task is not actionable.
            # Re-call the LLM once with a "plan too short" message; accept on
            # the second try regardless of length to avoid infinite retries.
            if len(parsed.steps) < _MIN_PLAN_STEPS and not short_plan_retried:
                short_plan_retried = True
                messages.append({"role": "assistant", "content": response.content or ""})
                messages.append({"role": "user", "content": _TOO_SHORT_PLAN_MESSAGE})
                continue
            # F19: if any ask_user answer was received during this plan() call
            # and the produced plan does not reference any non-stopword token
            # from any answer, retry the planner once with a corrective note.
            # Cap at one extra attempt; accept whatever comes back next.
            # Skipped when dedup-synthetic was emitted: the LLM has already been
            # told to "use sane defaults", so layering a competing "incorporate
            # the answer" directive doesn't fit that branch.
            if (
                received_answers
                and not answer_retry_used
                and not dedup_emitted
                and not any(_plan_references_answer(parsed, ans) for ans in received_answers)
            ):
                answer_retry_used = True
                messages.append({"role": "assistant", "content": response.content or ""})
                messages.append({"role": "user", "content": _ANSWER_NOT_INCORPORATED_MESSAGE})
                continue
            return parsed, response
        messages.append(
            {
                "role": "assistant",
                "content": response.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                    }
                    for tc in response.tool_calls
                ],
            }
        )
        for tc in response.tool_calls:
            if tc.name == "ask_user":
                content = _handle_ask_user_tool_call(
                    tc,
                    ask_user_callback,
                    asked_fingerprints,
                    received_answers,
                    dedup_emitted,
                )
            else:
                content = f"Error: tool {tc.name!r} not available in planning."
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": content,
                }
            )
    # Hit round cap without a final plan; fall back.
    return _fallback(task), last_response


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
