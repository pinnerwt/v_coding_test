from __future__ import annotations

import dataclasses
import json

import pytest

from agent.llm import ChatResponse, ToolCall, Usage
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


def _tool_call_response(name: str, arguments: dict, *, call_id: str = "tc-ask") -> ChatResponse:
    return ChatResponse(
        content=None,
        tool_calls=[ToolCall(id=call_id, name=name, arguments=json.dumps(arguments))],
        finish_reason="tool_calls",
        model="fake",
        usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        raw={},
    )


class _FakeLLM:
    def __init__(self, content: str):
        self._content = content

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        return _fake_response(self._content)


class _ScriptedLLM:
    """Returns each scripted ChatResponse in order; records every chat() call."""

    def __init__(self, responses: list[ChatResponse]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        self.calls.append({"messages": list(messages), "tools": tools})
        if not self._responses:
            raise AssertionError("ScriptedLLM exhausted")
        return self._responses.pop(0)


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


def test_plan_returns_fallback_when_steps_is_a_string():
    payload = json.dumps({"steps": "go home", "expected_end_state": "done"})
    llm = _FakeLLM(payload)
    result, _ = plan(task="find X", observation={}, llm=llm)
    assert result.steps == ["find X"]


def test_plan_returns_fallback_when_steps_contains_non_strings():
    payload = json.dumps({"steps": [1, 2, 3], "expected_end_state": "done"})
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


def test_replan_returns_fallback_when_steps_is_a_string():
    payload = json.dumps({"steps": "go home", "expected_end_state": "done"})
    prior = Plan(steps=["original step"], expected_end_state="original end")
    result, _ = replan(
        task="find X", observation={}, prior_plan=prior, reason="halt", llm=_FakeLLM(payload)
    )
    assert result.steps == ["find X"]


def test_replan_returns_fallback_when_steps_contains_non_strings():
    payload = json.dumps({"steps": [1, 2, 3], "expected_end_state": "done"})
    prior = Plan(steps=["original step"], expected_end_state="original end")
    result, _ = replan(
        task="find X", observation={}, prior_plan=prior, reason="halt", llm=_FakeLLM(payload)
    )
    assert result.steps == ["find X"]


def test_plan_strips_markdown_code_fence_around_json():
    """Qwen3.5-27B sometimes wraps its planner JSON in ```json ... ``` fences;
    _parse_plan must strip these so the real plan is used (not the fallback)."""
    payload = (
        "```json\n"
        '{"steps": ["ask the user: which branch?", "navigate to booking"], '
        '"expected_end_state": "reservation confirmed"}\n'
        "```"
    )
    llm = _FakeLLM(payload)
    result, _ = plan(task="book a table at 旭集", observation={}, llm=llm)
    assert result.steps == ["ask the user: which branch?", "navigate to booking"]
    assert result.expected_end_state == "reservation confirmed"


def test_plan_strips_unlabeled_code_fence_around_json():
    """Bare ``` ... ``` fences (no language tag) must also be stripped."""
    payload = '```\n{"steps": ["a", "b"], "expected_end_state": "done"}\n```'
    llm = _FakeLLM(payload)
    result, _ = plan(task="t", observation={}, llm=llm)
    assert result.steps == ["a", "b"]


def test_replan_strips_markdown_code_fence_around_json():
    payload = '```json\n{"steps": ["c"], "expected_end_state": "done"}\n```'
    prior = Plan(steps=["x"], expected_end_state="x")
    result, _ = replan(
        task="t", observation={}, prior_plan=prior, reason="halt", llm=_FakeLLM(payload)
    )
    assert result.steps == ["c"]


# ---------------------------------------------------------------------------
# planner-side ask_user: when info is insufficient, the planner must call the
# ask_user tool, receive an answer, and then produce the final plan with that
# answer baked in. ask_user is NOT a navigator step in the resulting plan.
# ---------------------------------------------------------------------------


def test_plan_calls_ask_user_callback_when_planner_emits_tool_call():
    """If the planner LLM emits an ask_user tool call, plan() must invoke the
    callback with the question, feed the answer back to the LLM, and then parse
    the LLM's follow-up JSON as the final plan."""
    captured: list[str] = []

    def _cb(q: str) -> str:
        captured.append(q)
        return "Tianmu"

    final_plan_json = json.dumps(
        {
            "steps": [
                "Navigate to https://inline.app/booking/旭集天母",
                "Pick a time slot",
            ],
            "expected_end_state": "reservation confirmed at Tianmu",
        }
    )
    llm = _ScriptedLLM(
        [
            _tool_call_response(
                "ask_user", {"questions": ["Which 旭集 location?"]}, call_id="tc-ask"
            ),
            _fake_response(final_plan_json),
        ]
    )

    result, resp = plan(
        task="book a table at 旭集",
        observation={"url": "about:blank"},
        llm=llm,
        ask_user_callback=_cb,
    )

    assert captured == ["Which 旭集 location?"], (
        f"callback must be invoked once with the planner's question, got {captured!r}"
    )
    assert result.steps == [
        "Navigate to https://inline.app/booking/旭集天母",
        "Pick a time slot",
    ], f"final plan must come from second LLM call, got {result.steps!r}"
    # The second call must include the assistant tool_call message AND the
    # tool-result message carrying the answer, so the LLM can plan around it.
    second_call_msgs = llm.calls[1]["messages"]
    tool_msgs = [m for m in second_call_msgs if m.get("role") == "tool"]
    assert any("Tianmu" in (m.get("content") or "") for m in tool_msgs), (
        f"answer 'Tianmu' must be fed back as a tool message, got {tool_msgs!r}"
    )
    assert resp is not None


def test_plan_does_not_call_ask_user_when_planner_returns_plan_directly():
    """Sufficient-info path: planner returns a JSON plan on the first call,
    callback is never invoked."""
    invoked: list[str] = []

    def _cb(q: str) -> str:
        invoked.append(q)
        return "should not be called"

    payload = json.dumps({"steps": ["go", "read"], "expected_end_state": "done"})
    llm = _ScriptedLLM([_fake_response(payload)])

    result, _ = plan(task="find X", observation={}, llm=llm, ask_user_callback=_cb)

    assert invoked == [], "callback must not be invoked when planner returns plan directly"
    assert result.steps == ["go", "read"]


def test_plan_handles_ask_user_with_no_callback_gracefully():
    """If the planner emits ask_user but no callback is wired, plan() must not
    crash; it should feed back an error tool message and let the planner fall
    back to its best-effort plan on the next turn."""
    payload = json.dumps({"steps": ["best effort", "verify"], "expected_end_state": "done"})
    llm = _ScriptedLLM(
        [
            _tool_call_response("ask_user", {"questions": ["which?"]}, call_id="tc-ask"),
            _fake_response(payload),
        ]
    )

    result, _ = plan(task="t", observation={}, llm=llm, ask_user_callback=None)

    assert result.steps == ["best effort", "verify"]


def test_plan_signature_accepts_ask_user_callback_kwarg():
    """Public surface: plan() must accept ask_user_callback as a keyword arg
    that defaults to None, so existing callers keep working."""
    import inspect

    from agent import plan as plan_mod

    sig = inspect.signature(plan_mod.plan)
    assert "ask_user_callback" in sig.parameters
    p = sig.parameters["ask_user_callback"]
    assert p.default is None


# ---------------------------------------------------------------------------
# Run context: planner sees current date, timezone, locale, and step budget
# ---------------------------------------------------------------------------


def test_plan_renders_run_context_into_user_message():
    """When a RunContext is passed, plan()'s user message must include the
    date, timezone, locale, and step_budget so the planner can plan around
    'now', region-specific entities, and how many navigation steps it has."""
    from agent.plan import RunContext

    payload = json.dumps({"steps": ["go", "read"], "expected_end_state": "done"})
    llm = _ScriptedLLM([_fake_response(payload)])
    ctx = RunContext(
        date="2026-04-30",
        timezone="Asia/Taipei",
        locale="zh-TW",
        step_budget=20,
    )

    plan(task="t", observation={}, llm=llm, context=ctx)

    user_msg = next(m for m in llm.calls[0]["messages"] if m.get("role") == "user")
    content = user_msg["content"]
    assert "2026-04-30" in content
    assert "Asia/Taipei" in content
    assert "zh-TW" in content
    assert "20" in content


def test_plan_signature_accepts_context_kwarg():
    """Public surface: plan() must accept context as a keyword arg that
    defaults to None, so existing callers keep working."""
    import inspect

    from agent import plan as plan_mod

    sig = inspect.signature(plan_mod.plan)
    assert "context" in sig.parameters
    assert sig.parameters["context"].default is None


def test_plan_omits_run_context_block_when_none():
    """When no context is provided, the planner user message must NOT contain
    a 'Run context:' block — preserves the no-context behavior."""
    payload = json.dumps({"steps": ["x", "y"], "expected_end_state": "done"})
    llm = _ScriptedLLM([_fake_response(payload)])

    plan(task="t", observation={}, llm=llm)

    user_msg = next(m for m in llm.calls[0]["messages"] if m.get("role") == "user")
    assert "Run context" not in user_msg["content"]


# ---------------------------------------------------------------------------
# F19: when ask_user supplies an answer, the resulting final plan must
# substring-reference at least one non-stopword token from that answer.
# Round-6 A3 trace (`task2/benchmark/feat-task2-sessions-ask-user-http/
# ask_user_smoke/round6/A3.json`) showed the planner re-stating the raw task
# verbatim after receiving "December 15, 2026, one-way" — neither the date
# nor "one-way" appeared in the produced plan. Structural retry, no prompt
# heuristics — applies to any task where an answer would otherwise be lost.
# ---------------------------------------------------------------------------


def test_plan_retries_when_initial_plan_drops_user_supplied_answer():
    """If the planner's first post-answer plan does not contain any non-stopword
    token from the answer, plan() must retry the LLM once with a corrective
    note, then accept the second plan even if it is still imperfect."""

    def _cb(_q: str) -> str:
        return "December 15, 2026, one-way"

    # First post-answer plan: ≥2 steps (so F11 short-plan retry doesn't fire),
    # but ignores the answer entirely.
    weak_plan = json.dumps(
        {
            "steps": [
                "Open a flight search site",
                "Search Taipei to Tokyo and report the cheapest fare",
            ],
            "expected_end_state": "fare reported",
        }
    )
    # Retry plan: weaves the date + one-way constraint in.
    strong_plan = json.dumps(
        {
            "steps": [
                "Open a flight search site",
                "Set departure date to December 15, 2026 and select one-way",
                "Search Taipei to Tokyo and report the cheapest fare",
            ],
            "expected_end_state": "fare reported",
        }
    )
    llm = _ScriptedLLM(
        [
            _tool_call_response("ask_user", {"questions": ["Dates?"]}, call_id="tc-ask"),
            _fake_response(weak_plan),
            _fake_response(strong_plan),
        ]
    )

    result, _ = plan(
        task="Book a flight from Taipei to Tokyo and return the cheapest fare.",
        observation={},
        llm=llm,
        ask_user_callback=_cb,
    )

    # Three LLM calls: ask_user → weak plan → corrective retry → strong plan.
    assert len(llm.calls) == 3, (
        f"expected exactly 3 LLM calls (ask_user, weak, retry), got {len(llm.calls)}"
    )
    assert any("December 15" in s for s in result.steps), (
        f"final plan must reference the user's answer, got {result.steps!r}"
    )

    # The retry message (third call's user-role payload) must call out the
    # missing answer so the LLM understands what to fix.
    third_msgs = llm.calls[2]["messages"]
    user_msgs = [m for m in third_msgs if m.get("role") == "user"]
    retry_note = " ".join(m.get("content") or "" for m in user_msgs)
    assert "answer" in retry_note.lower() and "incorporat" in retry_note.lower(), (
        f"retry must instruct the planner to incorporate the answer, got {retry_note!r}"
    )


def test_plan_does_not_retry_when_answer_already_referenced():
    """If the first post-answer plan already substring-references the answer,
    plan() must return immediately — no extra LLM call."""

    def _cb(_q: str) -> str:
        return "Tianmu"

    plan_with_answer = json.dumps(
        {
            "steps": [
                "Open the booking site",
                "Select the Tianmu branch and confirm",
            ],
            "expected_end_state": "reservation confirmed",
        }
    )
    llm = _ScriptedLLM(
        [
            _tool_call_response("ask_user", {"questions": ["Which location?"]}, call_id="tc-ask"),
            _fake_response(plan_with_answer),
        ]
    )

    result, _ = plan(
        task="book a table",
        observation={},
        llm=llm,
        ask_user_callback=_cb,
    )

    assert len(llm.calls) == 2, (
        f"no retry expected when plan already references the answer, got {len(llm.calls)}"
    )
    assert "Tianmu" in result.steps[1]


def test_plan_does_not_retry_when_answer_is_only_stopwords():
    """An answer like 'the one' has no enforceable content tokens after
    stopword removal; plan() must accept the first post-answer plan rather
    than retry indefinitely."""

    def _cb(_q: str) -> str:
        return "the one"

    payload = json.dumps(
        {"steps": ["start the task", "complete the task"], "expected_end_state": "done"}
    )
    llm = _ScriptedLLM(
        [
            _tool_call_response("ask_user", {"questions": ["Which?"]}, call_id="tc-ask"),
            _fake_response(payload),
        ]
    )

    result, _ = plan(task="t", observation={}, llm=llm, ask_user_callback=_cb)

    assert len(llm.calls) == 2, (
        f"stopword-only answers must not trigger retry, got {len(llm.calls)} calls"
    )
    assert result.steps == ["start the task", "complete the task"]


def test_plan_retry_only_runs_once_even_if_second_plan_also_misses():
    """For non-numeric answers the retry budget is one (F19 baseline) — accept
    whatever comes back next to avoid infinite loops. F28 only adds a second
    retry when the answer carries a digit-bearing token (dates, prices, IDs)."""

    def _cb(_q: str) -> str:
        return "Shinjuku"

    miss_plan = json.dumps(
        {"steps": ["Search for ramen", "Pick the top result"], "expected_end_state": "ok"}
    )
    second_miss = json.dumps(
        {
            "steps": ["Open Maps", "Search ramen and report the best"],
            "expected_end_state": "ok",
        }
    )
    llm = _ScriptedLLM(
        [
            _tool_call_response("ask_user", {"questions": ["Which area?"]}, call_id="tc-ask"),
            _fake_response(miss_plan),
            _fake_response(second_miss),
        ]
    )

    result, _ = plan(
        task="best ramen",
        observation={},
        llm=llm,
        ask_user_callback=_cb,
    )

    # Exactly one retry — third call. plan() accepts the second_miss even
    # though it still doesn't reference Shinjuku.
    assert len(llm.calls) == 3
    assert result.steps == ["Open Maps", "Search ramen and report the best"]


# ---------------------------------------------------------------------------
# F28: strengthen the F19 retry for date/numeric answers. Round-9 A3 trace
# (`task2/benchmark/feat-task2-sessions-ask-user-http/ask_user_smoke/round9/
# A3.json`) showed the planner producing two consecutive degenerate plans
# after `"December 15, 2026, one-way"` — F19's single retry was not enough.
# F28 adds (a) a stronger retry message naming the literal answer and the
# specific missing tokens, and (b) one extra retry gated on whether the
# answer contains any digit-bearing token (purely structural, no domain).
# ---------------------------------------------------------------------------


def test_f28_numeric_answer_triggers_second_retry_when_first_retry_still_misses():
    """When the answer is digit-bearing (date/price/id) and the first F19
    retry still produces a plan that drops the answer, F28 grants one more
    retry. Cap stays at 2 retries total — accept whatever comes back next."""

    def _cb(_q: str) -> str:
        return "December 15, 2026, one-way"

    miss = json.dumps(
        {
            "steps": [
                "Open a flight search site",
                "Search Taipei to Tokyo and report the cheapest fare",
            ],
            "expected_end_state": "fare reported",
        }
    )
    miss_again = json.dumps(
        {
            "steps": [
                "Open Google Flights",
                "Enter Taipei and Tokyo and find the cheapest fare",
            ],
            "expected_end_state": "fare reported",
        }
    )
    strong = json.dumps(
        {
            "steps": [
                "Open Google Flights",
                "Set departure date to December 15, 2026 and trip type to one-way",
                "Enter Taipei -> Tokyo and report the cheapest fare",
            ],
            "expected_end_state": "fare reported",
        }
    )
    llm = _ScriptedLLM(
        [
            _tool_call_response("ask_user", {"questions": ["Which date?"]}, call_id="tc-ask"),
            _fake_response(miss),
            _fake_response(miss_again),
            _fake_response(strong),
        ]
    )

    result, _ = plan(
        task="Book a flight from Taipei to Tokyo and return the cheapest fare.",
        observation={},
        llm=llm,
        ask_user_callback=_cb,
    )

    # 4 LLM calls: ask_user + miss + retry-1 (still misses) + retry-2 (succeeds).
    assert len(llm.calls) == 4, (
        f"F28: numeric answer that misses twice must receive a second retry; got {len(llm.calls)}"
    )
    assert any("December 15" in s for s in result.steps), result.steps


def test_f28_numeric_answer_second_retry_capped_third_attempt_accepted():
    """If the second retry STILL misses, plan() accepts the third attempt
    rather than retrying indefinitely."""

    def _cb(_q: str) -> str:
        return "Order #1234567"

    miss1 = json.dumps(
        {"steps": ["Open the order page", "Look up the order"], "expected_end_state": "ok"}
    )
    miss2 = json.dumps(
        {"steps": ["Open the dashboard", "Find the order"], "expected_end_state": "ok"}
    )
    miss3 = json.dumps(
        {"steps": ["Search the orders list", "Open the matching order"], "expected_end_state": "ok"}
    )
    llm = _ScriptedLLM(
        [
            _tool_call_response("ask_user", {"questions": ["Which order?"]}, call_id="tc-ask"),
            _fake_response(miss1),
            _fake_response(miss2),
            _fake_response(miss3),
        ]
    )

    result, _ = plan(task="open my order", observation={}, llm=llm, ask_user_callback=_cb)

    assert len(llm.calls) == 4, (
        f"F28: cap at two retries even if all attempts miss; got {len(llm.calls)}"
    )
    assert result.steps == ["Search the orders list", "Open the matching order"]


def test_f28_retry_message_names_the_literal_answer_and_missing_tokens():
    """F19's generic retry note ('the plan does not reference it') is too
    weak for date/quantity answers. F28 strengthens the message to include
    (a) the literal answer text and (b) the specific tokens that must
    appear, so the LLM has zero ambiguity about what to fix."""

    def _cb(_q: str) -> str:
        return "December 15, 2026, one-way"

    miss = json.dumps(
        {
            "steps": ["Open a flight search site", "Search and report the cheapest fare"],
            "expected_end_state": "ok",
        }
    )
    strong = json.dumps(
        {
            "steps": [
                "Open Google Flights",
                "Set departure date to December 15, 2026, trip type one-way",
                "Search and report the cheapest fare",
            ],
            "expected_end_state": "ok",
        }
    )
    llm = _ScriptedLLM(
        [
            _tool_call_response("ask_user", {"questions": ["Which date?"]}, call_id="tc-ask"),
            _fake_response(miss),
            _fake_response(strong),
        ]
    )

    plan(task="Book a flight", observation={}, llm=llm, ask_user_callback=_cb)

    # The third LLM call's retry message should include the literal answer
    # and at least one of the digit-bearing tokens (15, 2026).
    third_call = llm.calls[2]
    user_msgs = [m for m in third_call["messages"] if m.get("role") == "user"]
    retry_text = " ".join(m.get("content") or "" for m in user_msgs)
    assert "December 15, 2026, one-way" in retry_text, (
        f"F28: retry message must include the literal answer; got {retry_text!r}"
    )
    assert "2026" in retry_text or "15" in retry_text or "one-way" in retry_text, (
        f"F28: retry message must call out missing tokens; got {retry_text!r}"
    )


def test_f28_non_numeric_answer_does_not_get_a_second_retry():
    """F28's extra retry is gated on the presence of a digit-bearing token in
    the answer. For purely lexical answers (Shinjuku, Tianmu), the budget
    stays at one retry — F19's original behavior. This is the structural
    gate, not a domain rule."""

    def _cb(_q: str) -> str:
        return "Tianmu (天母店)"

    miss = json.dumps(
        {"steps": ["Open the booking site", "Pick a location"], "expected_end_state": "ok"}
    )
    miss_again = json.dumps(
        {"steps": ["Open the reservation portal", "Pick a branch"], "expected_end_state": "ok"}
    )
    llm = _ScriptedLLM(
        [
            _tool_call_response("ask_user", {"questions": ["Which location?"]}, call_id="tc-ask"),
            _fake_response(miss),
            _fake_response(miss_again),
        ]
    )

    plan(task="book a table", observation={}, llm=llm, ask_user_callback=_cb)

    # Exactly 3 LLM calls — F19's behavior preserved on lexical answers.
    assert len(llm.calls) == 3, (
        f"F28: non-numeric answer must not trigger a second retry; got {len(llm.calls)}"
    )


# ---------------------------------------------------------------------------
# I1: ask_user takes a list of questions, not a single bundled string. The
# planner declares all missing slots up front; the callback is invoked once
# per list item; the tool result is a Q&A block. Round-10 A3 motivated this:
# the planner emitted "What are your departure and return dates...?" — two
# slots in one string. With a list-shaped argument, bundling is impossible
# by construction.
# ---------------------------------------------------------------------------


def test_i1_ask_user_tool_schema_takes_questions_array():
    """The tool schema's required arg is `questions: array of string`, not the
    single-string `question` shape."""
    from agent.plan import _ASK_USER_TOOL

    params = _ASK_USER_TOOL["function"]["parameters"]
    assert params["required"] == ["questions"], params
    assert "question" not in params["properties"], params
    questions = params["properties"]["questions"]
    assert questions["type"] == "array"
    assert questions["items"]["type"] == "string"
    assert questions["minItems"] == 1
    assert questions["maxItems"] == 3


def test_i1_ask_user_with_two_questions_invokes_callback_twice_in_order():
    """A single ask_user tool call with two questions fires the callback twice
    in list order; both answers are accumulated; the tool result is a Q&A
    block that names both Qs and their As."""
    asked: list[str] = []

    def _cb(q: str) -> str:
        asked.append(q)
        return {"Which branch?": "天母店 (Tianmu)", "What date?": "Saturday, May 9"}.get(q, "?")

    plan_json = json.dumps(
        {
            "steps": [
                "Open booking site",
                "Pick 天母店 branch on Saturday, May 9",
                "Confirm reservation",
            ],
            "expected_end_state": "booked",
        }
    )
    llm = _ScriptedLLM(
        [
            _tool_call_response(
                "ask_user",
                {"questions": ["Which branch?", "What date?"]},
                call_id="tc-multi",
            ),
            _fake_response(plan_json),
        ]
    )

    result, _ = plan(task="Book a table", observation={}, llm=llm, ask_user_callback=_cb)

    # Callback fired in list order with each question.
    assert asked == ["Which branch?", "What date?"], asked
    # Resulting plan incorporates BOTH answers (F19 token check).
    assert any("天母店" in s or "Tianmu" in s for s in result.steps)
    assert any("Saturday" in s or "May 9" in s for s in result.steps)

    # The tool message that was fed back to the LLM contains both Q&A pairs.
    tool_msg_content = ""
    for msg in llm.calls[1]["messages"]:
        if msg.get("role") == "tool":
            tool_msg_content += msg.get("content", "")
    assert "Which branch?" in tool_msg_content
    assert "天母店" in tool_msg_content or "Tianmu" in tool_msg_content
    assert "What date?" in tool_msg_content
    assert "Saturday" in tool_msg_content or "May 9" in tool_msg_content


def test_i1_ask_user_with_single_question_still_works():
    """A list of length 1 is the common case — single ambiguity, single ask."""
    asked: list[str] = []

    def _cb(q: str) -> str:
        asked.append(q)
        return "天母店 (Tianmu)"

    plan_json = json.dumps(
        {"steps": ["Open booking site", "Pick 天母店 branch"], "expected_end_state": "ok"}
    )
    llm = _ScriptedLLM(
        [
            _tool_call_response("ask_user", {"questions": ["Which branch?"]}, call_id="tc-one"),
            _fake_response(plan_json),
        ]
    )

    plan(task="Book a table", observation={}, llm=llm, ask_user_callback=_cb)

    assert asked == ["Which branch?"]


def test_i1_ask_user_rejects_legacy_single_question_shape():
    """If the LLM emits the old `{question: str}` shape, the tool result is an
    error message that names the new shape, and the callback never fires.
    The next planner call gets a chance to re-issue with the correct shape."""
    asked: list[str] = []

    def _cb(q: str) -> str:
        asked.append(q)
        return "should not happen"

    plan_json = json.dumps({"steps": ["Open site", "Read result"], "expected_end_state": "ok"})
    llm = _ScriptedLLM(
        [
            _tool_call_response("ask_user", {"question": "Which?"}, call_id="tc-legacy"),
            _fake_response(plan_json),
        ]
    )

    plan(task="t", observation={}, llm=llm, ask_user_callback=_cb)

    assert asked == [], asked
    tool_msg_content = ""
    for msg in llm.calls[1]["messages"]:
        if msg.get("role") == "tool":
            tool_msg_content += msg.get("content", "")
    assert "questions" in tool_msg_content.lower()


def test_i1_ask_user_empty_list_returns_error():
    """Empty questions list → error, callback not fired."""
    asked: list[str] = []

    def _cb(q: str) -> str:
        asked.append(q)
        return "x"

    plan_json = json.dumps({"steps": ["s1", "s2"], "expected_end_state": "ok"})
    llm = _ScriptedLLM(
        [
            _tool_call_response("ask_user", {"questions": []}, call_id="tc-empty"),
            _fake_response(plan_json),
        ]
    )

    plan(task="t", observation={}, llm=llm, ask_user_callback=_cb)

    assert asked == []


def test_i1_ask_user_runtime_caps_list_at_three():
    """If the LLM bypasses the schema's maxItems=3 (some local LLMs ignore
    it), the runtime check rejects the call without invoking the callback."""
    asked: list[str] = []

    def _cb(q: str) -> str:
        asked.append(q)
        return "x"

    plan_json = json.dumps({"steps": ["s1", "s2"], "expected_end_state": "ok"})
    llm = _ScriptedLLM(
        [
            _tool_call_response(
                "ask_user",
                {"questions": ["Q1?", "Q2?", "Q3?", "Q4?"]},
                call_id="tc-over",
            ),
            _fake_response(plan_json),
        ]
    )

    plan(task="t", observation={}, llm=llm, ask_user_callback=_cb)

    assert asked == [], f"runtime cap of 3 must reject 4-item list; callback fired for: {asked}"


def test_i1_dedup_applies_per_list_item_when_a_question_was_already_asked():
    """When a second ask_user round overlaps a question from the first round,
    only the overlapping list items get the dedup-synthetic; new items still
    invoke the callback. This preserves F18-style "ask once per slot" while
    not throwing away the LLM's progress on the rest."""
    asked: list[str] = []

    def _cb(q: str) -> str:
        asked.append(q)
        return f"answer to {q}"

    plan_json = json.dumps({"steps": ["Open site", "Continue"], "expected_end_state": "ok"})
    llm = _ScriptedLLM(
        [
            _tool_call_response("ask_user", {"questions": ["Which branch?"]}, call_id="tc-1"),
            _tool_call_response(
                "ask_user",
                {"questions": ["Which branch?", "What date?"]},
                call_id="tc-2",
            ),
            _fake_response(plan_json),
        ]
    )

    plan(task="t", observation={}, llm=llm, ask_user_callback=_cb)

    # First round asked branch; second round overlaps on branch (dedup) and
    # adds date (callback fires).
    assert asked == ["Which branch?", "What date?"], asked
