"""Tests for agent.replay — decision replay harness.

TDD: all tests in this file were written before agent/replay.py existed.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from agent.replay import ReplayDivergence, ReplayResult, StubBrowser, StubLLMClient, replay_run
from agent.trace import (
    DecisionEvent,
    LLMCallEvent,
    ObservationEvent,
    Run,
    _any_event_adapter,
)

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "traces" / "simple_goto_done.jsonl"


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
    assert len(stub._page.url) > 0
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


def _make_chat_response(tool_name: str, args: dict):
    """Helper to create a minimal ChatResponse for testing."""
    from agent.llm import ChatResponse, ToolCall, Usage

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

    mutated_lines = []
    mutated = False
    for line in lines:
        obj = json.loads(line)
        if not mutated and obj.get("kind") == "decision" and obj.get("tool") == "goto":
            obj["tool"] = "read"
            mutated = True
        mutated_lines.append(json.dumps(obj))

    assert mutated, "Expected to mutate a decision line"

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

    mutated_lines = []
    mutated = False
    for line in lines:
        obj = json.loads(line)
        if not mutated and obj.get("kind") == "decision" and obj.get("tool") == "goto":
            obj["tool"] = "read"
            mutated = True
        mutated_lines.append(json.dumps(obj))

    mutated_file = tmp_path / "mutated_stepid.jsonl"
    mutated_file.write_text("\n".join(mutated_lines) + "\n")

    result = replay_run(mutated_file)
    assert result.matched is False
    assert result.first_divergence is not None
    # step_id must come from the recorded DecisionEvent (fixture has "step-1")
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
