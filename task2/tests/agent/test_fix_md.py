"""Tests for the five ask-user-smoke fixes documented in task2/fix.md.

F1 — plan dedup: planner does not invoke ask_user_callback twice for the same
     normalized question; instead it feeds back a synthetic answer that tells
     the LLM to stop re-asking.
F2 — plan_cursor gate on done: a `done` whose run never advanced past the
     first half of a multi-step plan is rejected as premature.
F3 — superlative gating: planner system prompt explicitly mentions
     superlatives ("best", "cheapest", "nearest", ...).
F4 — one-slot-per-ask: planner system prompt enforces one slot per
     `ask_user` call.
F5 — status reconciliation: a `done` whose result payload self-reports a
     hard failure (`status: "unable_to_complete"` etc.) downgrades the
     RunResult to status="failed".
"""

from __future__ import annotations

import json

from agent.browser import Browser
from agent.llm import ChatResponse, ToolCall, Usage
from agent.loop import RunResult, loop
from agent.plan import _PLAN_SYSTEM, plan

# --- shared fakes ---------------------------------------------------------


def _fake_response(content: str) -> ChatResponse:
    return ChatResponse(
        content=content,
        tool_calls=[],
        finish_reason="stop",
        model="fake",
        usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        raw={},
    )


def _tool_call_response(name: str, arguments: dict, *, call_id: str) -> ChatResponse:
    return ChatResponse(
        content=None,
        tool_calls=[ToolCall(id=call_id, name=name, arguments=json.dumps(arguments))],
        finish_reason="tool_calls",
        model="fake",
        usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        raw={},
    )


class _ScriptedLLM:
    def __init__(self, responses: list[ChatResponse]):
        self._responses = list(responses)
        self.calls: list[dict] = []

    def chat(self, messages: list[dict], *, tools=None, **_kwargs) -> ChatResponse:
        self.calls.append({"messages": list(messages), "tools": tools})
        if not self._responses:
            raise AssertionError("ScriptedLLM exhausted")
        return self._responses.pop(0)


# --- F1 -------------------------------------------------------------------


def test_f1_plan_does_not_invoke_callback_twice_for_same_question():
    """If the LLM asks essentially the same question twice in a row, plan()
    must surface the question to the user only once. The second LLM round
    receives a synthetic tool message instead of another callback round-trip,
    so the LLM stops re-asking and produces a plan with sane defaults.
    """
    captured: list[str] = []

    def _cb(q: str) -> str:
        captured.append(q)
        return "天母店 (Tianmu)"

    final_plan = json.dumps(
        {"steps": ["go to inline.app/booking/旭集天母", "pick a time"], "expected_end_state": "ok"}
    )
    llm = _ScriptedLLM(
        [
            _tool_call_response(
                "ask_user",
                {"question": "Which Inparadise location and how many people?"},
                call_id="tc-1",
            ),
            _tool_call_response(
                "ask_user",
                {"question": "How many people will be dining?"},
                call_id="tc-2",
            ),
            _tool_call_response(
                "ask_user",
                {"question": "Please confirm the number of people."},
                call_id="tc-3",
            ),
            _fake_response(final_plan),
        ]
    )

    result, _ = plan(task="book at 旭集", observation={}, llm=llm, ask_user_callback=_cb)

    assert len(captured) == 1, (
        f"callback must be invoked at most once even when the LLM re-asks; got {captured!r}"
    )
    assert result.steps == ["go to inline.app/booking/旭集天母", "pick a time"]


def test_f1_synthetic_answer_tells_llm_to_stop_asking():
    """The synthetic tool message fed back on the second ask_user must clearly
    instruct the LLM to stop using ask_user, so it has a fighting chance of
    producing a plan instead of re-asking again.
    """

    def _cb(_q: str) -> str:
        return "first answer"

    final_plan = json.dumps({"steps": ["x", "y"], "expected_end_state": "z"})
    llm = _ScriptedLLM(
        [
            _tool_call_response("ask_user", {"question": "Which one?"}, call_id="tc-1"),
            _tool_call_response("ask_user", {"question": "Which one?"}, call_id="tc-2"),
            _fake_response(final_plan),
        ]
    )
    plan(task="t", observation={}, llm=llm, ask_user_callback=_cb)

    third_call_msgs = llm.calls[2]["messages"]
    tool_msgs = [m for m in third_call_msgs if m.get("role") == "tool"]
    raw = tool_msgs[-1]["content"]
    synthetic = raw.lower()
    assert "already asked" in synthetic or "do not" in synthetic, (
        "second ask_user must receive a synthetic answer telling the LLM not to re-ask; "
        f"got {raw!r}"
    )


# --- F3 / F4 (prompt-level contract tests) --------------------------------


def test_f3_planner_prompt_mentions_superlatives():
    """The planner prompt must list superlative triggers so the LLM treats
    'best/cheapest/nearest/top/most' as ambiguity signals.
    """
    lowered = _PLAN_SYSTEM.lower()
    assert "best" in lowered and "cheapest" in lowered, _PLAN_SYSTEM
    assert "superlative" in lowered or "ranking" in lowered, _PLAN_SYSTEM


def test_f4_planner_prompt_enforces_one_slot_per_ask():
    """The planner prompt must require one slot per ask_user call."""
    lowered = _PLAN_SYSTEM.lower()
    assert "one slot" in lowered or "single slot" in lowered or "one missing" in lowered, (
        _PLAN_SYSTEM
    )


# --- F2 / F5 (loop-level integration) -------------------------------------


def _tool_call(name: str, args: dict, *, call_id: str) -> ToolCall:
    return ToolCall(id=call_id, name=name, arguments=json.dumps(args))


def _response_with_tool_call(tc: ToolCall) -> ChatResponse:
    return ChatResponse(
        content=None,
        tool_calls=[tc],
        finish_reason="tool_calls",
        model="fake",
        usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        raw={},
    )


def test_f5_done_with_unable_to_complete_status_downgrades_to_failed(
    fixture_server, playwright_chromium
):
    """When the agent calls `done` but its own result payload self-reports a
    hard failure status, the loop must return RunResult.status='failed' so
    eval scoring and the SSE terminal event don't silently mark it as a pass.
    """
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    from tests.agent.test_loop import _FakeLLMClient

    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-1")),
        _response_with_tool_call(
            _tool_call(
                "done",
                {
                    "result": {
                        "status": "unable_to_complete",
                        "reason": "captcha + DB error",
                    },
                    "evidence": {"url": fixture_url, "text_snippet": "Hello, loop"},
                    "evaluation_previous_action": "failed",
                    "evaluation_reason": "blocked by captcha",
                    "next_goal": "report final answer",
                },
                call_id="tc-2",
            )
        ),
    ]
    fake_llm = _FakeLLMClient(responses)
    with Browser(playwright_browser=playwright_chromium) as browser:
        result: RunResult = loop("task", browser, fake_llm, max_steps=4)

    assert result.status == "failed", (
        "done with result.status='unable_to_complete' must downgrade the run to failed; "
        f"got {result.status!r}"
    )


def test_f2_done_rejected_when_plan_cursor_never_advanced_past_half(
    fixture_server, playwright_chromium
):
    """Replay an A3-style scenario: a 6-step plan, agent does ONE goto with
    plan_cursor=1, then calls done with stale evidence. The loop must reject
    the done as premature (cursor never reached 3 of 6) and continue. The
    second `done` from the LLM is only accepted because it tries again.
    """
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    # The planner stub in _FakeLLMClient produces a 1-step plan, so we need to
    # patch in a multi-step plan response. We use a custom LLM that intercepts
    # planner calls.
    from agent.llm import Usage as _U
    from tests.agent.test_loop import _FakeLLMClient

    multi_step_plan = ChatResponse(
        content=json.dumps(
            {
                "steps": [
                    "Navigate to flights.example.com",
                    "Fill in 'Where from?' with Taipei",
                    "Fill in 'Where to?' with Tokyo",
                    "Set departure date",
                    "Click search",
                    "Read cheapest fare from results",
                ],
                "expected_end_state": "fare known",
            }
        ),
        tool_calls=[],
        finish_reason="stop",
        model="fake",
        usage=_U(prompt_tokens=1, completion_tokens=1, total_tokens=2),
        raw={},
    )

    class _MultiStepPlanLLM(_FakeLLMClient):
        def chat(self, messages, *, tools=None, **kwargs):
            from tests.agent.test_loop import _is_planner_call

            if tools is None or _is_planner_call(messages):
                return multi_step_plan
            return super().chat(messages, tools=tools, **kwargs)

    bad_done = _tool_call(
        "done",
        {
            "result": {"cheapest_fare": "NT$6,343"},
            "evidence": {"url": fixture_url, "text_snippet": "Find flights from Taipei"},
            "evaluation_previous_action": "success",
            "evaluation_reason": "navigated to flights page",
            "next_goal": "report final answer",
        },
        call_id="tc-bad-done",
    )
    follow_up_fail = _tool_call("fail", {"reason": "no real data on page"}, call_id="tc-fail")
    responses = [
        _response_with_tool_call(
            _tool_call("goto", {"url": fixture_url, "plan_cursor": 1}, call_id="tc-1")
        ),
        _response_with_tool_call(bad_done),
        _response_with_tool_call(follow_up_fail),
    ]
    fake_llm = _MultiStepPlanLLM(responses)
    events: list = []
    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("find cheapest fare", browser, fake_llm, max_steps=6, events=events)

    # The loop should reject the premature done, then accept the fail.
    from agent.trace import SupervisorEvent

    sup_events = [e for e in events if isinstance(e, SupervisorEvent)]
    assert any(e.classified_as == "premature_done" for e in sup_events), (
        f"expected a premature_done supervisor event for cursor << plan length; got {sup_events!r}"
    )
    assert result.status == "failed"


# --- F3 (one-shot superlative example) ------------------------------------


def test_f3_planner_prompt_has_concrete_superlative_example():
    """Live behavior on Qwen3.5-27B did not change after merely listing the
    trigger words. The prompt must include a concrete one-shot example
    demonstrating that 'Find the best X' should produce an `ask_user`
    asking for the ranking criterion. The example must literally pair a
    'best/cheapest/...'-style task with a follow-up 'by what?' question
    inside a contiguous span of the prompt."""
    text = _PLAN_SYSTEM
    lowered = text.lower()
    # Find an example block that pairs a superlative-task instance with a
    # by-what?-style ask. Allow a flexible window so the example can be
    # phrased naturally.
    superlatives = ["best", "cheapest", "nearest", "top", "most"]
    asks = ["by what", "by which", "what criteria", "what criterion", "ranked by", "rated by"]
    found = False
    for sup in superlatives:
        i = 0
        while True:
            j = lowered.find(sup, i)
            if j < 0:
                break
            window = lowered[j : j + 220]
            if any(a in window for a in asks):
                found = True
                break
            i = j + 1
        if found:
            break
    assert found, (
        "prompt must include a one-shot example pairing a superlative task "
        "(best/cheapest/nearest/top/most) with a follow-up 'by what?'-style "
        f"ask within ~200 chars; current prompt:\n{text}"
    )


# --- F6 (supervisor-halt circuit breaker) ---------------------------------


def test_f6_circuit_breaker_terminates_on_repeated_premature_done(
    fixture_server, playwright_chromium
):
    """When supervisor halts the same (tool, classification) pair repeatedly,
    the loop must terminate with a 'failed' status and a circuit-breaker
    reason rather than burning through max_steps. Reproduces the round-2 U4
    pattern where Qwen retried `done` 12 times after F2 rejections."""
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    from tests.agent.test_loop import _FakeLLMClient

    def _bad_done(i: int) -> ToolCall:
        return _tool_call(
            "done",
            {
                "result": {"x": i},
                "evidence": {"url": fixture_url, "text_snippet": "Hello, loop"},
                "evaluation_previous_action": "success",
                "evaluation_reason": "ostensibly retrieved",
                # `next_goal` containing a navigation verb (search/find) trips
                # the T1 premature_done gate at every step regardless of
                # step_num, so the supervisor halts every iteration.
                "next_goal": "search for the next page",
            },
            call_id=f"tc-bad-{i}",
        )

    responses = [_response_with_tool_call(_bad_done(i)) for i in range(20)]
    fake_llm = _FakeLLMClient(responses)
    events: list = []
    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("task", browser, fake_llm, max_steps=15, events=events)

    assert result.status == "failed", (
        f"circuit breaker must terminate stuck loop with status=failed, got {result.status!r}"
    )
    assert result.steps < 10, (
        f"circuit breaker should fire well before max_steps=15, used {result.steps} steps"
    )
    reason = (result.reason or "").lower()
    assert "circuit" in reason or "stuck" in reason or "rejected" in reason, (
        f"reason must indicate the circuit breaker fired; got {result.reason!r}"
    )


# --- F7 (don't `done` after consecutive action failures) ------------------


def test_f7_done_rejected_after_two_consecutive_action_failures(
    fixture_server, playwright_chromium
):
    """If the last two action outcomes were timeout/error, the `done` handler
    must reject the call. Reproduces the round-2 A1 pattern where the agent
    tried `done` after two `click` timeouts on a Chinese-text element."""
    fixture_url = f"{fixture_server}/loop_happy_path.html"
    from tests.agent.test_loop import _FakeLLMClient

    bogus_click_1 = _tool_call(
        "click",
        {"intent": "the 訂位確認 button"},  # intent that won't resolve
        call_id="tc-c1",
    )
    bogus_click_2 = _tool_call(
        "click",
        {"intent": "the 訂位確認 link"},
        call_id="tc-c2",
    )
    # done after both clicks failed — should be rejected by F7
    fab_done = _tool_call(
        "done",
        {
            "result": {"booked": True},
            "evidence": {"url": fixture_url, "text_snippet": "Hello, loop"},
            "evaluation_previous_action": "success",  # bypasses T1 gate
            "evaluation_reason": "ostensibly booked",
            "next_goal": "report final answer",
        },
        call_id="tc-fab",
    )
    follow_fail = _tool_call("fail", {"reason": "stuck"}, call_id="tc-fail")

    responses = [
        _response_with_tool_call(_tool_call("goto", {"url": fixture_url}, call_id="tc-g")),
        _response_with_tool_call(bogus_click_1),
        _response_with_tool_call(bogus_click_2),
        _response_with_tool_call(fab_done),
        _response_with_tool_call(follow_fail),
    ]
    fake_llm = _FakeLLMClient(responses)
    events: list = []
    with Browser(playwright_browser=playwright_chromium) as browser:
        result = loop("task", browser, fake_llm, max_steps=8, events=events)

    from agent.trace import SupervisorEvent

    sup_events = [e for e in events if isinstance(e, SupervisorEvent)]
    classes = [e.classified_as for e in sup_events]
    assert any(c in {"premature_done", "done_after_failure"} for c in classes), (
        f"expected done to be rejected after two action failures; sup events: {classes!r}"
    )
    assert result.status == "failed"


# --- F8 (CJK locator fallback) --------------------------------------------


def test_f8_cjk_textmatch_fallback_for_link_with_chinese_label(fixture_server, playwright_chromium):
    """The standard tiers miss non-ASCII accessible-name matches when the
    DOM uses an `<a>` with Chinese text and no aria-label. A final-tier
    verbatim textContent substring fallback must locate the element."""
    fixture_url = f"{fixture_server}/locate_cjk_fallback.html"
    from agent.locate import locate

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        # Standard "link" tier may or may not match — but the fallback must.
        result = locate(browser._page, "網路訂位 link")

    assert result is not None
    # The selector must resolve back to exactly one element on the live page
    assert result.selector


def test_f8_cjk_fallback_for_role_button_without_accessible_name(
    fixture_server, playwright_chromium
):
    """A `<span role="button">` with only inner Chinese text and no
    aria-label must still be locatable via textContent."""
    fixture_url = f"{fixture_server}/locate_cjk_fallback.html"
    from agent.locate import locate

    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        result = locate(browser._page, "搜尋 Google 地圖 button")

    assert result is not None
    assert result.selector


# --- F11 (plan must contain at least two steps) ---------------------------


def test_f11_one_step_plan_triggers_replan_request():
    """Round-4 A3 evidence: after `ask_user` round-trip, the planner returned
    `steps=["Book a flight from Taipei to Tokyo and return the cheapest fare."]`
    — one bullet that just restates the task. The agent then ran without a
    real plan and stalled. `plan()` must reject a 1-step plan and re-call
    the LLM once for a longer plan."""
    short_plan = json.dumps({"steps": ["Book a flight."], "expected_end_state": "booked"})
    long_plan = json.dumps(
        {
            "steps": [
                "Navigate to a flight search site",
                "Enter origin, destination, date",
                "Read the cheapest fare from results",
            ],
            "expected_end_state": "fare retrieved",
        }
    )
    llm = _ScriptedLLM([_fake_response(short_plan), _fake_response(long_plan)])

    result, _ = plan(task="Book a flight TPE→NRT", observation={}, llm=llm)

    assert len(result.steps) >= 2, f"final plan must have >=2 steps; got {result.steps!r}"
    assert result.steps[0].startswith("Navigate")
    assert len(llm.calls) == 2, (
        f"planner must re-call LLM once on a too-short plan; got {len(llm.calls)} calls"
    )


def test_f11_two_step_plan_does_not_replan():
    """A plan with >= 2 steps is acceptable; the planner must NOT re-call."""
    plan_json = json.dumps({"steps": ["go to site", "click button"], "expected_end_state": "done"})
    llm = _ScriptedLLM([_fake_response(plan_json)])

    result, _ = plan(task="t", observation={}, llm=llm)

    assert result.steps == ["go to site", "click button"]
    assert len(llm.calls) == 1


# --- F14 (verify L_textmatch fires through the loop's ladder) -------------


def test_f14_loop_ladder_emits_l_textmatch_event_on_l1_l2_miss(fixture_server, playwright_chromium):
    """Round-4 smoke evidence (A1 trace) showed L1_ax and L2_dom miss
    events on a CJK-link intent, then terminal failure — no L_textmatch
    event ever fired. The loop's `_locate_via_ladder` must invoke the
    textmatch tier after L2 miss (and emit a corresponding LocateEvent)
    before giving up. Asserts:
      - L1_ax miss event
      - L2_dom miss event
      - L_textmatch hit event with a non-empty selector
    """
    from agent.loop import _locate_via_ladder
    from agent.trace import LocateEvent
    from tests.agent.test_loop import (  # type: ignore[no-untyped-import]
        _make_mock_supervisor_next_tier,
        _make_writer_with_run,
    )

    run_id = "f14-textmatch"
    writer = _make_writer_with_run(run_id)
    supervisor = _make_mock_supervisor_next_tier()

    fixture_url = f"{fixture_server}/locate_cjk_fallback.html"
    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        result = _locate_via_ladder(
            browser._page,
            "網路訂位 link",
            supervisor,
            trace_writer=writer,
            run_id=run_id,
            step_id=f"{run_id}:step-1",
        )

    assert result is not None
    assert result.tier == "L_textmatch"
    assert result.selector

    locate_events = [e for e in writer.iter_events(run_id) if isinstance(e, LocateEvent)]
    tiers_outcomes = [(e.tier, e.outcome) for e in locate_events]
    assert ("L1_ax", "miss") in tiers_outcomes
    assert ("L2_dom", "miss") in tiers_outcomes
    assert ("L_textmatch", "hit") in tiers_outcomes
    writer.close()


# --- F13 (textbox locator must match role=combobox inputs) ----------------


def test_f13_textbox_intent_matches_combobox_role_at_l1(fixture_server, playwright_chromium):
    """Round-4 A6/U1 evidence: Google Maps and google.com homepage render
    their search input as `role=combobox`, not `role=textbox`. The agent's
    `intent="the search textbox"` therefore L1+L2 missed and stalled.
    L1_ax must accept either role for textbox-shaped intents."""
    from agent.locate import locate_l1

    fixture_url = f"{fixture_server}/locate_combobox.html"
    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        result = locate_l1(browser._page, role="textbox", name="Search")

    assert result is not None
    assert result.tier == "L1_ax"
    assert result.role in {"textbox", "combobox"}


def test_f13_textbox_intent_matches_combobox_via_full_locate(
    fixture_server, playwright_chromium
):
    """End-to-end through `locate()`: intent 'Search textbox' on a page that
    only has a `role=combobox` editable div must resolve to that element."""
    from agent.locate import locate

    fixture_url = f"{fixture_server}/locate_combobox.html"
    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        result = locate(browser._page, "Search textbox")

    assert result is not None
    assert result.selector
    # Selector must resolve to the combobox div on the live page.
    with Browser(playwright_browser=playwright_chromium) as b2:
        b2.goto(fixture_url)
        loc = b2._page.locator(result.selector)
        assert loc.count() == 1
        attr = loc.first.evaluate("el => el.getAttribute('role')")
        assert attr == "combobox"


# --- F12 (read(intent=) auto-falls back to read() on locate error) ---------


def test_f12_read_intent_unlocatable_falls_back_to_body(fixture_server, playwright_chromium):
    """Round-4 U1/U4 evidence: `read intent="..."` reliably errored on dense
    pages; the LLM then re-issued `read(find=...)` or `read()` and burned a
    full LLM round-trip per occurrence. When intent-locate fails, the
    dispatcher must internally fall back to a no-args body read so the LLM
    sees usable text on the first try, not an error."""
    from agent.loop import _dispatch
    from agent.supervisor import Supervisor

    fixture_url = f"{fixture_server}/loop_happy_path.html"
    with Browser(playwright_browser=playwright_chromium) as browser:
        browser.goto(fixture_url)
        # An intent that has no matching role on the page — should NOT bubble
        # the locator error back to the LLM; it should return body text.
        out = _dispatch(
            "read",
            {"intent": "the nonexistent_zzzqq button"},
            browser,
            Supervisor(),
        )

    assert not out.lower().startswith("error"), (
        f"read(intent=) on an unlocatable element must auto-fall-back, not error; got {out!r}"
    )
    # Body text must contain the heading from the fixture.
    assert "Hello" in out
