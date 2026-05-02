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
    "If information is INSUFFICIENT, call the `ask_user` tool with the "
    "argument `questions`: a JSON array where each element is ONE focused "
    "question for ONE missing slot. Shape:\n"
    '  - one slot:    {"questions": ["<question about slot A>"]}\n'
    '  - two slots:   {"questions": ["<question about slot A>", '
    '"<question about slot B>"]}\n'
    "Always emit `questions` as an array, even when there is only one. "
    "Do NOT pack multiple slots into one question string with 'and' — "
    "split them into separate array items instead. "
    "Ask only what the task actually requires; do not over-ask. Do NOT "
    "guess the missing information. Do NOT include 'ask the user: ...' "
    "as a plan step — that step happens here, in planning, not during "
    "navigation. You get exactly ONE round of `ask_user`: list every "
    "missing slot you can see in that single call's `questions` array. "
    "After the user answers, the `ask_user` tool will no longer be "
    "available — produce a plan from the Q&A you have, picking sane "
    "defaults for any still-missing fields. "
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

_PLAN_SYSTEM_NO_ASK = (
    "You are a planning assistant for a browser agent. Produce a concrete "
    "step-by-step plan using the task and any clarifying Q&A in the "
    "conversation above. Pick sane defaults for any still-missing fields. "
    "Respond with ONLY a JSON object: "
    '{"steps": ["step 1", ...], "expected_end_state": "..."}'
)

_REPLAN_SYSTEM = (
    "You are a planning assistant. The prior plan failed partway through. "
    "Given the task, current state, prior steps, and failure reason, "
    "produce a revised short ordered list of steps. "
    'Respond with ONLY a JSON object: {"steps": ["step 1", ...], "expected_end_state": "..."}'
)

_MAX_QUESTIONS_PER_ASK = 3

_ASK_USER_TOOL = {
    "type": "function",
    "function": {
        "name": "ask_user",
        "description": (
            "Ask the human user one or more clarifying questions to resolve "
            "ambiguity in the task before planning concrete steps. List each "
            "missing slot as a separate question. Do not list more questions "
            "than the task actually requires."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "questions": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                    "maxItems": _MAX_QUESTIONS_PER_ASK,
                    "description": "One specific clarifying question per missing slot.",
                }
            },
            "required": ["questions"],
        },
    },
}

_MAX_ASK_USER_ROUNDS = 1
_MIN_PLAN_STEPS = 2
_TOO_SHORT_PLAN_MESSAGE = (
    "Your previous plan had fewer than 2 concrete steps. A plan that "
    "just restates the task is not actionable. Produce a new plan with "
    "at least 2 distinct navigation/interaction steps."
)


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
) -> str:
    """Resolve an ask_user tool call into the string content for the tool message.

    The tool argument is `questions: list[str]`. Each list item is a separate
    slot; the callback fires once per item, in order. The result is a Q&A
    block — `Q1: ...\\nA1: ...\\n\\nQ2: ...\\nA2: ...` — so the LLM never has
    to remember positional pairing.

    Per-item dedup: if a list item near-matches a question asked in an earlier
    round of this plan() invocation, that item gets the dedup-synthetic answer
    while the other items still go through the callback.
    """
    try:
        args = json.loads(tool_call.arguments) if tool_call.arguments else {}
    except json.JSONDecodeError:
        return "Error: ask_user arguments were not valid JSON."
    if "question" in args and "questions" not in args:
        return (
            "Error: ask_user requires a `questions` list (e.g. "
            '`{"questions": ["..."]}`). The single-string `question` shape '
            "is not supported. Re-issue with one question per missing slot."
        )
    questions = args.get("questions")
    if not isinstance(questions, list) or not questions:
        return "Error: ask_user requires a non-empty `questions` list of strings."
    if not all(isinstance(q, str) and q.strip() for q in questions):
        return "Error: every item in `questions` must be a non-empty string."
    if len(questions) > _MAX_QUESTIONS_PER_ASK:
        return (
            f"Error: ask_user accepts at most {_MAX_QUESTIONS_PER_ASK} "
            "questions per call. Re-issue with the most blocking slots only."
        )
    if ask_user_callback is None:
        return (
            "Error: ask_user is not available in this run (no callback wired). "
            "Produce a best-effort plan from the task as stated."
        )

    qa_pairs: list[tuple[str, str]] = []
    for question in questions:
        fingerprint = _normalize_question(question)
        if fingerprint in asked_fingerprints:
            qa_pairs.append((question, _DEDUP_SYNTHETIC_ANSWER))
            continue
        asked_fingerprints.add(fingerprint)
        try:
            answer = str(ask_user_callback(question))
        except Exception as exc:  # noqa: BLE001
            qa_pairs.append((question, f"Error: ask_user callback raised: {exc}"))
            continue
        qa_pairs.append((question, answer))

    return _format_qa_block(qa_pairs)


def _format_qa_block(qa_pairs: list[tuple[str, str]]) -> str:
    """Render a list of (question, answer) into a numbered Q&A block."""
    lines: list[str] = []
    for idx, (q, a) in enumerate(qa_pairs, start=1):
        if lines:
            lines.append("")
        lines.append(f"Q{idx}: {q}")
        lines.append(f"A{idx}: {a}")
    return "\n".join(lines)


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
    short_plan_retried = False
    asked_rounds = 0
    for _ in range(_MAX_ASK_USER_ROUNDS + 2):
        # After the planner has used its one ask_user round, drop the tool
        # AND swap the system prompt so it stops instructing the LLM to call
        # ask_user. Otherwise prompt and tool list contradict.
        ask_available = asked_rounds < _MAX_ASK_USER_ROUNDS
        tools_for_round = [_ASK_USER_TOOL] if ask_available else []
        messages[0] = {
            "role": "system",
            "content": _PLAN_SYSTEM if ask_available else _PLAN_SYSTEM_NO_ASK,
        }
        response = llm.chat(messages, tools=tools_for_round)
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
            return parsed, response
        if not ask_available:
            # ask_user not advertised this round but the LLM emitted it
            # anyway. Don't fire the callback; nudge once and re-ask for
            # a plan. The tool plumbing (assistant tool_call + tool result)
            # is intentionally NOT appended — keeping the message stack
            # clean of any reference to the absent tool.
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Produce the final plan now from the information "
                        "already provided. Do not request more clarification."
                    ),
                }
            )
            asked_rounds += 1
            continue
        # Legitimate round-0 ask_user. Resolve every tool_call into Q&A
        # text and append it as a single user message — the LLM doesn't
        # need to know it came via a tool round.
        for tc in ask_calls:
            qa_content = _handle_ask_user_tool_call(
                tc, ask_user_callback, asked_fingerprints
            )
            messages.append({"role": "user", "content": qa_content})
        asked_rounds += 1
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
