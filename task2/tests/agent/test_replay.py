"""Tests for agent.replay — decision replay harness.

TDD: all tests in this file were written before agent/replay.py existed.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from agent.llm import ChatResponse, ToolCall, Usage
from agent.loop import _build_system_prompt, loop
from agent.replay import ReplayDivergence, ReplayResult, StubBrowser, StubLLMClient, replay_run
from agent.trace import (
    DecisionEvent,
    LLMCallEvent,
    ObservationEvent,
    Run,
    _any_event_adapter,
)

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "traces" / "simple_goto_done.jsonl"


def _default_run_dict(run_id: str, task: str) -> dict:
    return {
        "run_id": run_id,
        "task": task,
        "expect_schema": None,
        "budget": {"steps": 20, "usd": 1.0, "seconds": 120},
        "llm": {
            "base_url": "http://stub.local",
            "model": "stub-model",
            "temperature": 0.0,
            "seed": None,
        },
        "agent_version": "0.0.1-test",
        "started_at": "2024-01-01T00:00:00Z",
        "ended_at": None,
        "status": None,
        "final": None,
        "totals": None,
    }


def _mutate_decision_tool(lines: list[str], old_tool: str, new_tool: str) -> list[str]:
    """Rewrite the first DecisionEvent line whose tool == old_tool to new_tool."""
    out: list[str] = []
    mutated = False
    for line in lines:
        obj = json.loads(line)
        if not mutated and obj.get("kind") == "decision" and obj.get("tool") == old_tool:
            obj["tool"] = new_tool
            mutated = True
        out.append(json.dumps(obj))
    assert mutated, f"Expected to mutate a decision line with tool={old_tool!r}"
    return out


# ---------------------------------------------------------------------------
# Dataclass frozen tests
# ---------------------------------------------------------------------------


def test_replay_divergence_is_frozen():
    div = ReplayDivergence(
        step_id="s1",
        expected={"tool": "goto", "args": {"url": "http://a"}},
        actual={"tool": "read", "args": {}},
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        div.step_id = "s2"  # type: ignore[misc]


def test_replay_result_is_frozen():
    result = ReplayResult(matched=True, steps=2, first_divergence=None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.matched = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# StubBrowser tests
# ---------------------------------------------------------------------------


def test_stub_browser_page_attributes():
    stub = StubBrowser()
    assert isinstance(stub._page.url, str)
    result = stub._page.evaluate("() => document.body.innerText")
    assert isinstance(result, str)


def test_stub_browser_goto_noop():
    stub = StubBrowser()
    # Should not raise
    stub.goto("http://example.com")


def test_stub_browser_read_returns_str():
    stub = StubBrowser()
    result = stub.read("body")
    assert isinstance(result, str)


def test_stub_browser_screenshot_returns_bytes():
    stub = StubBrowser()
    result = stub.screenshot()
    assert isinstance(result, bytes)


def test_stub_browser_context_manager():
    with StubBrowser() as stub:
        assert stub is not None
        stub.goto("http://example.com")


# ---------------------------------------------------------------------------
# StubLLMClient tests
# ---------------------------------------------------------------------------


def _make_chat_response(tool_name: str, args: dict) -> ChatResponse:
    """Helper to create a minimal ChatResponse for testing."""
    return ChatResponse(
        content=None,
        tool_calls=[ToolCall(id="tc-test", name=tool_name, arguments=json.dumps(args))],
        finish_reason="tool_calls",
        model="stub",
        usage=Usage(0, 0, 0),
        raw={},
    )


def test_stub_llm_client_returns_in_order():

    r1 = _make_chat_response("goto", {"url": "http://a"})
    r2 = _make_chat_response(
        "done",
        {"result": {}, "evidence": {"url": "http://a", "text_snippet": "a"}},
    )

    stub = StubLLMClient([r1, r2])
    assert stub.chat([]) is r1
    assert stub.chat([]) is r2
    assert stub.responses_consumed == [r1, r2]


def test_stub_llm_client_exhausted_returns_noop():

    r1 = _make_chat_response("goto", {"url": "http://a"})
    stub = StubLLMClient([r1])

    _first = stub.chat([])
    second = stub.chat([])  # exhausted

    assert second.tool_calls == []
    assert second.finish_reason == "stop"


# ---------------------------------------------------------------------------
# Fixture parsing tests
# ---------------------------------------------------------------------------


def test_fixture_parses_without_error():
    lines = FIXTURE_PATH.read_text().strip().splitlines()
    run = Run.model_validate_json(lines[0])
    assert run.run_id == "run-test-001"
    events = [_any_event_adapter.validate_json(line) for line in lines[1:]]
    assert len(events) == 6


def test_fixture_event_sequence():
    lines = FIXTURE_PATH.read_text().strip().splitlines()
    events = [_any_event_adapter.validate_json(line) for line in lines[1:]]

    observations = [e for e in events if isinstance(e, ObservationEvent)]
    llm_calls = [e for e in events if isinstance(e, LLMCallEvent) and e.purpose == "decide"]
    decisions = [e for e in events if isinstance(e, DecisionEvent)]

    assert len(observations) >= 1
    assert len(llm_calls) == 2
    assert len(decisions) == 2
    assert decisions[0].tool == "goto"
    assert decisions[1].tool == "done"


# ---------------------------------------------------------------------------
# replay_run integration tests
# ---------------------------------------------------------------------------


def test_replay_run_matched_on_unmodified_fixture():
    result = replay_run(FIXTURE_PATH)
    assert result.matched is True
    assert result.first_divergence is None


def test_replay_run_steps_count():
    result = replay_run(FIXTURE_PATH)
    assert result.steps == 2


def test_replay_run_divergence_on_mutated_fixture(tmp_path):
    """Mutate first DecisionEvent.tool from 'goto' to 'read' — expect divergence."""
    lines = FIXTURE_PATH.read_text().strip().splitlines()
    mutated_lines = _mutate_decision_tool(lines, "goto", "read")

    mutated_file = tmp_path / "mutated.jsonl"
    mutated_file.write_text("\n".join(mutated_lines) + "\n")

    result = replay_run(mutated_file)
    assert result.matched is False
    assert result.first_divergence is not None
    assert result.first_divergence.expected["tool"] == "read"
    assert result.first_divergence.actual["tool"] == "goto"


def test_replay_run_divergence_step_id_from_recorded(tmp_path):
    """first_divergence.step_id SHALL equal the step_id of the recorded DecisionEvent."""
    lines = FIXTURE_PATH.read_text().strip().splitlines()
    mutated_lines = _mutate_decision_tool(lines, "goto", "read")

    mutated_file = tmp_path / "mutated_stepid.jsonl"
    mutated_file.write_text("\n".join(mutated_lines) + "\n")

    result = replay_run(mutated_file)
    assert result.matched is False
    assert result.first_divergence is not None
    assert result.first_divergence.step_id == "step-1"


def test_replay_run_count_mismatch_more_replayed(tmp_path):
    """If the replay produces more decisions than recorded, matched SHALL be False.

    Constructed by removing the second DecisionEvent from the fixture while keeping
    both LLMCallEvents: recorded_decisions = 1, but loop calls chat() twice
    (replayed_pairs = 2).  steps = min(1, 2) = 1; first match at step 0 passes;
    then count divergence triggers matched=False.
    """
    lines = FIXTURE_PATH.read_text().strip().splitlines()

    filtered_lines = []
    removed = False
    for line in lines:
        obj = json.loads(line)
        if not removed and obj.get("kind") == "decision" and obj.get("tool") == "done":
            removed = True
            continue  # drop second DecisionEvent so recorded count = 1
        filtered_lines.append(line)

    assert removed, "Expected to remove the second DecisionEvent"

    short_file = tmp_path / "short_decisions.jsonl"
    short_file.write_text("\n".join(filtered_lines) + "\n")

    result = replay_run(short_file)
    assert result.matched is False
    assert result.steps == 1  # min(1 recorded, 2 replayed)


def test_replay_run_detects_prompt_drift(tmp_path):
    """If the prompt loop.py sends differs from the recorded prompt, replay SHALL diverge.

    Mutates the recorded system prompt in the fixture; loop.py still sends the original
    system prompt, so replay must surface a prompt-level divergence (not silently match
    on identical tool-call sequence).
    """
    lines = FIXTURE_PATH.read_text().strip().splitlines()
    out: list[str] = []
    mutated = False
    for line in lines:
        obj = json.loads(line)
        if not mutated and obj.get("kind") == "llm_call" and obj.get("purpose") == "decide":
            messages = obj["prompt"]["messages"]
            for m in messages:
                if m.get("role") == "system":
                    m["content"] = m["content"] + "\n\nADDITIONAL POLICY: do not click."
                    mutated = True
                    break
        out.append(json.dumps(obj))
    assert mutated, "Expected to mutate the system message of the first decide LLMCallEvent"

    drifted = tmp_path / "drifted.jsonl"
    drifted.write_text("\n".join(out) + "\n")

    result = replay_run(drifted)
    assert result.matched is False
    assert result.first_divergence is not None
    assert result.first_divergence.kind == "prompt"
    assert result.first_divergence.step_id == "step-1"


def _record_fixture(tmp_path: Path, task: str, responses: list) -> Path:
    """Run loop.py with a recording LLM to produce a self-consistent trace fixture.

    Captures every prompt loop.py sends and pairs it with the canned response, then
    writes a JSONL trace whose `prompt`/`response` shape matches what TraceWriter
    would produce. DecisionEvents are emitted only for tool-call responses (no-tool
    turns produce an LLMCallEvent but no DecisionEvent), mirroring loop.py's
    semantics.
    """

    rec = StubLLMClient(responses)
    with StubBrowser() as br:
        loop(task=task, browser=br, llm_client=rec, max_steps=len(responses) + 2)

    run = _default_run_dict("run-rec-001", task)

    events: list[dict] = []
    seq = 0
    decision_idx = 0
    current_url = ""  # mirrors StubBrowser default; updated after each goto response.
    for i, (prompt_msgs, resp) in enumerate(zip(rec.prompts_consumed, responses, strict=True)):
        step_id = f"step-{i + 1}"
        seq += 1
        events.append(
            {
                "run_id": run["run_id"],
                "seq": seq,
                "ts": f"2024-01-01T00:00:{seq:02d}Z",
                "step_id": step_id,
                "kind": "observation",
                "url": current_url,
                "title": "",
                "ax_tree_digest": "",
                "ax_fingerprint": "",
                "screenshot_ref": "",
                "viewport": {"width": 1280, "height": 720},
            }
        )
        seq += 1
        llm_call_id = f"lc-{i + 1}"
        recorded_resp_dict: dict = {
            "content": resp.content,
            "finish_reason": resp.finish_reason,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": tc.arguments},
                }
                for tc in resp.tool_calls
            ],
        }
        events.append(
            {
                "run_id": run["run_id"],
                "seq": seq,
                "ts": f"2024-01-01T00:00:{seq:02d}Z",
                "step_id": step_id,
                "kind": "llm_call",
                "llm_call_id": llm_call_id,
                "purpose": "decide",
                "model": "stub-model",
                "base_url": "http://stub.local",
                "prompt": {"messages": prompt_msgs},
                "response": recorded_resp_dict,
                "tokens": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "usd": 0.0,
                "ms": 0,
            }
        )
        if resp.tool_calls:
            decision_idx += 1
            tc = resp.tool_calls[0]
            tc_args = json.loads(tc.arguments) if tc.arguments else {}
            seq += 1
            events.append(
                {
                    "run_id": run["run_id"],
                    "seq": seq,
                    "ts": f"2024-01-01T00:00:{seq:02d}Z",
                    "step_id": step_id,
                    "kind": "decision",
                    "intent": f"decision-{decision_idx}",
                    "tool": tc.name,
                    "args": tc_args,
                    "rationale": "recorded by test helper",
                    "llm_call_id": llm_call_id,
                }
            )
            if tc.name == "goto" and isinstance(tc_args.get("url"), str):
                current_url = tc_args["url"]

    fixture_path = tmp_path / "recorded.jsonl"
    fixture_path.write_text("\n".join([json.dumps(run)] + [json.dumps(e) for e in events]) + "\n")
    return fixture_path


def test_replay_run_ignores_no_tool_decide_turns(tmp_path):
    """A decide LLMCallEvent with no tool_calls SHALL NOT be counted as a replayed decision.

    Build a self-consistent fixture where loop.py emits a no-tool 'thinking' chat turn
    before each tool call. Recorded DecisionEvents = 2 (goto, done); decide LLMCallEvents
    = 3 (no-tool, goto, done). Replay must align the 2 tool-call responses to the 2
    DecisionEvents and report match — not append ('', {}) for the no-tool turn.
    """
    no_tool = ChatResponse(
        content="Let me think.",
        tool_calls=[],
        finish_reason="stop",
        model="stub",
        usage=Usage(0, 0, 0),
        raw={},
    )
    goto = _make_chat_response("goto", {"url": "http://stub.local/"})
    done_args = {
        "result": {"title": "Stub"},
        "evidence": {"url": "http://stub.local/", "text_snippet": "S"},
    }
    done = _make_chat_response("done", done_args)

    fixture_path = _record_fixture(
        tmp_path, "go to example and return title", [no_tool, goto, done]
    )

    result = replay_run(fixture_path)
    assert result.matched is True, f"Expected match; got divergence={result.first_divergence!r}"
    assert result.first_divergence is None


def test_replay_run_detects_extra_chat_calls(tmp_path):
    """Loop calling chat() more times than the recording SHALL surface a divergence.

    Construct a recording that ends after a single no-tool decide turn (no DecisionEvent
    emitted, recording stops mid-flight). When replay runs, loop.py will keep calling
    chat() until max_steps because no done/fail tool ever arrives — those extra calls
    must be reported, not silently capped at min(recorded, consumed).
    """
    observation = {"url": "http://stub.local/", "text": ""}
    first_prompt = [
        {"role": "system", "content": _build_system_prompt("task")},
        {"role": "user", "content": f"Current state: {json.dumps(observation)}"},
    ]

    run = _default_run_dict("run-rec-001", "task")
    events = [
        {
            "run_id": run["run_id"],
            "seq": 1,
            "ts": "2024-01-01T00:00:01Z",
            "step_id": "step-1",
            "kind": "observation",
            "url": "http://stub.local/",
            "title": "",
            "ax_tree_digest": "",
            "ax_fingerprint": "",
            "screenshot_ref": "",
            "viewport": {"width": 1280, "height": 720},
        },
        {
            "run_id": run["run_id"],
            "seq": 2,
            "ts": "2024-01-01T00:00:02Z",
            "step_id": "step-1",
            "kind": "llm_call",
            "llm_call_id": "lc-1",
            "purpose": "decide",
            "model": "stub-model",
            "base_url": "http://stub.local",
            "prompt": {"messages": first_prompt},
            "response": {"content": "thinking", "finish_reason": "stop", "tool_calls": []},
            "tokens": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "usd": 0.0,
            "ms": 0,
        },
    ]
    fixture = tmp_path / "truncated.jsonl"
    fixture.write_text("\n".join([json.dumps(run)] + [json.dumps(e) for e in events]) + "\n")

    result = replay_run(fixture)
    assert result.matched is False
    assert result.first_divergence is not None
    assert result.first_divergence.kind == "prompt"


def test_replay_run_compares_messages_only_not_full_prompt_payload(tmp_path):
    """Extra fields in recorded LLMCallEvent.prompt (tools/model/...) SHALL NOT diverge.

    The trace schema allows `prompt: dict[str, Any]` to carry arbitrary keys beyond
    `messages`. Replay only sees `messages` (what loop.py passes to chat), so the
    diff must compare just the `messages` field — not the whole payload.
    """
    lines = FIXTURE_PATH.read_text().strip().splitlines()
    out: list[str] = []
    augmented = False
    for line in lines:
        obj = json.loads(line)
        if obj.get("kind") == "llm_call" and obj.get("purpose") == "decide":
            obj["prompt"]["tools"] = [
                {"type": "function", "function": {"name": "extra", "description": "x"}}
            ]
            obj["prompt"]["model"] = "stub-model"
            augmented = True
        out.append(json.dumps(obj))
    assert augmented, "Expected to augment at least one decide LLMCallEvent prompt"

    fixture = tmp_path / "augmented.jsonl"
    fixture.write_text("\n".join(out) + "\n")

    result = replay_run(fixture)
    assert result.matched is True, f"Expected match; got divergence={result.first_divergence!r}"
    assert result.first_divergence is None


def test_replay_run_skips_malformed_tool_arguments(tmp_path):
    """Recorded tool_call.arguments that aren't valid JSON or aren't a JSON object
    SHALL NOT raise during replay. loop.py treats both as recoverable and does not
    dispatch the tool, so the trace records the LLMCallEvent without a paired
    DecisionEvent — replay must mirror that, not crash on json.loads.
    """
    task = "malformed-args"
    run = _default_run_dict("run-rec-001", task)

    bad_response = ChatResponse(
        content=None,
        tool_calls=[ToolCall(id="tc-bad", name="goto", arguments="{not json")],
        finish_reason="tool_calls",
        model="stub",
        usage=Usage(0, 0, 0),
        raw={},
    )
    done_args = {
        "result": {},
        "evidence": {"url": "http://stub.local/", "text_snippet": "ok"},
    }
    done_response = _make_chat_response("done", done_args)

    rec = StubLLMClient([bad_response, done_response])
    with StubBrowser() as br:
        loop(task=task, browser=br, llm_client=rec, max_steps=4)

    events: list[dict] = []
    for i, (prompt_msgs, resp) in enumerate(
        zip(rec.prompts_consumed, [bad_response, done_response], strict=True)
    ):
        seq = i * 2 + 1
        events.append(
            {
                "run_id": run["run_id"],
                "seq": seq,
                "ts": f"2024-01-01T00:00:{seq:02d}Z",
                "step_id": f"step-{i + 1}",
                "kind": "llm_call",
                "llm_call_id": f"lc-{i + 1}",
                "purpose": "decide",
                "model": "stub-model",
                "base_url": "http://stub.local",
                "prompt": {"messages": prompt_msgs},
                "response": {
                    "content": resp.content,
                    "finish_reason": resp.finish_reason,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.name, "arguments": tc.arguments},
                        }
                        for tc in resp.tool_calls
                    ],
                },
                "tokens": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
                "usd": 0.0,
                "ms": 0,
            }
        )
    events.append(
        {
            "run_id": run["run_id"],
            "seq": 4,
            "ts": "2024-01-01T00:00:04Z",
            "step_id": "step-2",
            "kind": "decision",
            "intent": "decision-1",
            "tool": "done",
            "args": done_args,
            "rationale": "after recovering from malformed args",
            "llm_call_id": "lc-2",
        }
    )

    fixture = tmp_path / "malformed_args.jsonl"
    fixture.write_text("\n".join([json.dumps(run)] + [json.dumps(e) for e in events]) + "\n")

    result = replay_run(fixture)
    assert result.matched is True, f"Expected match; got divergence={result.first_divergence!r}"


def test_replay_run_handles_multiple_tool_calls_per_response(tmp_path):
    """loop.py iterates every tool_call in response.tool_calls. Replay must too.

    Build a fixture where a single decide LLMCallEvent carries two tool_calls
    (a `read` followed by `done`) with a DecisionEvent for each — the recorded
    trace shape that emerges when an LLM batches calls. Replay's old behaviour
    only looked at tool_calls[0], so the second decision would go missing and
    produce a false count divergence; the fix must surface a match.
    """
    task = "batch task"
    run = _default_run_dict("run-rec-001", task)

    read_call = {"id": "tc-1", "type": "function", "function": {"name": "read", "arguments": "{}"}}
    done_args = {
        "result": {"v": 1},
        "evidence": {"url": "http://stub.local/", "text_snippet": "x"},
    }
    done_call = {
        "id": "tc-2",
        "type": "function",
        "function": {"name": "done", "arguments": json.dumps(done_args)},
    }

    observation = {"url": "http://stub.local/", "text": ""}
    first_prompt = [
        {"role": "system", "content": _build_system_prompt(task)},
        {"role": "user", "content": f"Current state: {json.dumps(observation)}"},
    ]

    events = [
        {
            "run_id": run["run_id"],
            "seq": 1,
            "ts": "2024-01-01T00:00:01Z",
            "step_id": "step-1",
            "kind": "observation",
            "url": "http://stub.local/",
            "title": "",
            "ax_tree_digest": "",
            "ax_fingerprint": "",
            "screenshot_ref": "",
            "viewport": {"width": 1280, "height": 720},
        },
        {
            "run_id": run["run_id"],
            "seq": 2,
            "ts": "2024-01-01T00:00:02Z",
            "step_id": "step-1",
            "kind": "llm_call",
            "llm_call_id": "lc-1",
            "purpose": "decide",
            "model": "stub-model",
            "base_url": "http://stub.local",
            "prompt": {"messages": first_prompt},
            "response": {
                "content": None,
                "finish_reason": "tool_calls",
                "tool_calls": [read_call, done_call],
            },
            "tokens": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "usd": 0.0,
            "ms": 0,
        },
        {
            "run_id": run["run_id"],
            "seq": 3,
            "ts": "2024-01-01T00:00:03Z",
            "step_id": "step-1",
            "kind": "decision",
            "intent": "decision-1",
            "tool": "read",
            "args": {},
            "rationale": "batched read",
            "llm_call_id": "lc-1",
        },
        {
            "run_id": run["run_id"],
            "seq": 4,
            "ts": "2024-01-01T00:00:04Z",
            "step_id": "step-1",
            "kind": "decision",
            "intent": "decision-2",
            "tool": "done",
            "args": done_args,
            "rationale": "batched done",
            "llm_call_id": "lc-1",
        },
    ]
    fixture = tmp_path / "batched_tool_calls.jsonl"
    fixture.write_text("\n".join([json.dumps(run)] + [json.dumps(e) for e in events]) + "\n")

    result = replay_run(fixture)
    assert result.matched is True, f"Expected match; got divergence={result.first_divergence!r}"


def test_stub_browser_goto_updates_url():
    """browser.goto(url) SHALL update the stub page's url so subsequent _observe
    calls in loop.py see the new URL — otherwise prompts drift after navigation.
    """
    stub = StubBrowser()
    stub.goto("https://example.com/path")
    assert stub._page.url == "https://example.com/path"


def test_replay_run_tracks_navigated_url_in_prompt(tmp_path):
    """After a recorded `goto` the next prompt's URL must reflect the navigated URL.

    Records a trace by running loop with a real navigation, then replays. If the
    stub page kept its initial URL across goto, the post-navigation prompt would
    diverge even though loop's behaviour is unchanged.
    """
    task = "navigate then done"

    target_url = "https://example.com/page"
    goto_response = _make_chat_response("goto", {"url": target_url})
    done_args = {
        "result": {},
        "evidence": {"url": target_url, "text_snippet": "ok"},
    }
    done_response = _make_chat_response("done", done_args)

    rec = StubLLMClient([goto_response, done_response])
    with StubBrowser() as br:
        loop(task=task, browser=br, llm_client=rec, max_steps=4)

    second_prompt = rec.prompts_consumed[1]
    user_state = second_prompt[-1]["content"]
    assert target_url in user_state, (
        f"After goto({target_url!r}), the next observation prompt must include the "
        f"navigated URL. Got: {user_state!r}"
    )

    fixture_path = _record_fixture(tmp_path, task, [goto_response, done_response])
    result = replay_run(fixture_path)
    assert result.matched is True, f"Expected match; got divergence={result.first_divergence!r}"


def test_replay_run_handles_intent_based_read_without_crashing(tmp_path):
    """A recorded `read` with non-empty intent SHALL NOT crash replay.

    loop._dispatch routes intent-driven reads through locate_l1/locate_l2, which
    call page.get_by_role / page.locator. The stub page must expose enough of
    that surface to raise a clean LocatorMiss (which loop turns into a tool
    error message) instead of AttributeError.
    """
    task = "find the heading"
    read_response = _make_chat_response("read", {"intent": "the heading"})
    done_args = {
        "result": {},
        "evidence": {"url": "http://stub.local/", "text_snippet": "ok"},
    }
    done_response = _make_chat_response("done", done_args)

    fixture_path = _record_fixture(tmp_path, task, [read_response, done_response])
    result = replay_run(fixture_path)
    assert result.matched is True, f"Expected match; got divergence={result.first_divergence!r}"


def test_replay_run_preserves_empty_string_assistant_content(tmp_path):
    """A recorded response with content="" must replay as content="".

    Coercing "" to None changes the next prompt's assistant message
    (`{"content": ""}` vs `{"content": null}`) and produces a false prompt
    divergence even though loop's behaviour is unchanged.
    """
    task = "empty content"
    empty_then_done = ChatResponse(
        content="",
        tool_calls=[ToolCall(id="tc-1", name="goto", arguments=json.dumps({"url": "http://x"}))],
        finish_reason="tool_calls",
        model="stub",
        usage=Usage(0, 0, 0),
        raw={},
    )
    done_args = {
        "result": {},
        "evidence": {"url": "http://x", "text_snippet": "ok"},
    }
    done_response = _make_chat_response("done", done_args)

    fixture_path = _record_fixture(tmp_path, task, [empty_then_done, done_response])

    result = replay_run(fixture_path)
    assert result.matched is True, f"Expected match; got divergence={result.first_divergence!r}"


def test_stub_browser_no_playwright_import():
    """agent.replay SHALL NOT directly import playwright.

    Verified by inspecting the module's import chain rather than sys.modules
    state (which is polluted by other tests that use playwright fixtures).
    """
    import importlib.util
    import types

    # Walk every module imported by agent.replay (direct imports only).
    # playwright should not appear as a direct dependency.
    replay_spec = importlib.util.find_spec("agent.replay")
    assert replay_spec is not None, "agent.replay must be importable"

    import agent.replay as replay_mod

    direct_imports = {
        name for name, obj in vars(replay_mod).items() if isinstance(obj, types.ModuleType)
    }
    # None of the directly bound names should be playwright
    assert not any("playwright" in name for name in direct_imports), (
        f"agent.replay directly references a playwright module: {direct_imports}"
    )
