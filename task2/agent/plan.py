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
    "question for ONE missing slot. Examples of correct shape:\n"
    '  - one slot:    {"questions": ["Which city or branch?"]}\n'
    '  - two slots:   {"questions": ["Which branch?", "What date?"]}\n'
    '  - three slots: {"questions": ["Which city?", "What date?", "How '
    'many guests?"]}\n'
    "Always emit `questions` as an array, even when there is only one. "
    "Do NOT pack multiple slots into one question string with 'and' "
    '(wrong: {"questions": ["What is the date and how many guests?"]}). '
    "Ask only what the task actually requires; do not over-ask. Do NOT "
    "guess the missing information. Do NOT include 'ask the user: ...' "
    "as a plan step — that step happens here, in planning, not during "
    "navigation. After the user answers, you may call `ask_user` again "
    "if the answer revealed a NEW ambiguity (a different slot you didn't "
    "know about); but if you already asked about a particular slot once "
    "and the answer did not fill it, do NOT ask again about that same "
    "slot — pick a sane default and proceed. "
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


def _answer_has_numeric_token(answer: str) -> bool:
    """True if any non-stopword token in the answer contains a digit. Used
    by F28 to gate a second retry: date/price/id answers are easy for the
    planner to silently drop, so they get one extra correction round."""
    return any(any(ch.isdigit() for ch in tok) for tok in _answer_tokens(answer))


def _plan_references_answer(plan: Plan, answer: str) -> bool:
    """True if the plan references the user's answer.

    F19 baseline: at least one non-stopword token from `answer` must appear
    as a case-insensitive substring in any plan step or expected_end_state.

    F28 stricter rule for digit-bearing answers: when the answer contains
    any digit-bearing token (date/price/id), require at least one of THOSE
    specifically — planners often retain a generic noun (e.g. 'order')
    while silently dropping the actual number.

    If the answer has no enforceable tokens after stopword removal, returns
    True (no enforcement).
    """
    tokens = _answer_tokens(answer)
    if not tokens:
        return True
    haystack = (" ".join(plan.steps) + " " + plan.expected_end_state).lower()
    digit_tokens = [tok for tok in tokens if any(ch.isdigit() for ch in tok)]
    if digit_tokens:
        return any(tok in haystack for tok in digit_tokens)
    return any(tok in haystack for tok in tokens)


def _build_answer_not_incorporated_message(answers: list[str], plan_obj: Plan) -> str:
    """F28: construct a retry message that names the literal answer text and
    the specific non-stopword tokens that must appear in the next plan."""
    haystack = (" ".join(plan_obj.steps) + " " + plan_obj.expected_end_state).lower()
    parts = [
        "The user's answer must be incorporated into the plan; the plan you "
        "just produced does not reference it. Produce a new plan whose steps "
        "explicitly use the user's answer."
    ]
    for ans in answers:
        missing = [tok for tok in _answer_tokens(ans) if tok not in haystack]
        if not missing:
            continue
        parts.append(
            f' The user answered: "{ans}". '
            f"Your next plan MUST contain at least one of these tokens "
            f"verbatim: {', '.join(missing)}."
        )
    return "".join(parts)


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
            dedup_emitted.append(True)
            qa_pairs.append((question, _DEDUP_SYNTHETIC_ANSWER))
            continue
        asked_fingerprints.add(fingerprint)
        try:
            answer = str(ask_user_callback(question))
        except Exception as exc:  # noqa: BLE001
            qa_pairs.append((question, f"Error: ask_user callback raised: {exc}"))
            continue
        received_answers.append(answer)
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
    received_answers: list[str] = []
    dedup_emitted: list[bool] = []
    short_plan_retried = False
    answer_retries_used = 0
    for _ in range(_MAX_ASK_USER_ROUNDS + 2):
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
            # F19/F28: if any ask_user answer was received during this plan()
            # call and the produced plan does not reference any non-stopword
            # token from any answer, retry the planner with a corrective note.
            # F19 grants 1 retry. F28 grants a 2nd retry only when the answer
            # contains a digit-bearing token (date/price/id) — those answers
            # are structurally easy to drop. Cap at 2 retries; accept whatever
            # comes back next. Skipped when dedup-synthetic was emitted: the
            # LLM has already been told to "use sane defaults", so layering a
            # competing "incorporate the answer" directive doesn't fit.
            if (
                received_answers
                and not dedup_emitted
                and not any(_plan_references_answer(parsed, ans) for ans in received_answers)
            ):
                allow_second = any(_answer_has_numeric_token(ans) for ans in received_answers)
                retry_cap = 2 if allow_second else 1
                if answer_retries_used < retry_cap:
                    answer_retries_used += 1
                    retry_msg = _build_answer_not_incorporated_message(received_answers, parsed)
                    messages.append({"role": "assistant", "content": response.content or ""})
                    messages.append({"role": "user", "content": retry_msg})
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
