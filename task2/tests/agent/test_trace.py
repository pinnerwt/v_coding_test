"""Tests for agent.trace module — red first, then green."""

from __future__ import annotations

import json

import pytest
from pydantic import TypeAdapter

from agent.trace import (
    ActEvent,
    AnyEvent,
    DecisionEvent,
    DoneEvent,
    LLMCallEvent,
    LocateEvent,
    ObservationEvent,
    PlanEvent,
    Run,
    SeqError,
    SupervisorEvent,
    TraceWriter,
    redact,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

RUN_ID = "01HZXYZ0000000000000000000"
TS = "2024-01-01T00:00:00Z"


def _run_full() -> Run:
    return Run(
        run_id=RUN_ID,
        task="search for cats",
        expect_schema={"type": "object"},
        budget={"steps": 20, "usd": 1.0, "seconds": 300},
        llm={"base_url": "http://localhost:8090", "model": "qwen3", "temperature": 0.0, "seed": 42},
        agent_version="abc123",
        started_at=TS,
        ended_at="2024-01-01T00:01:00Z",
        status="succeeded",
        final={"result": {"answer": "cats"}, "evidence": {}, "failure": None},
        totals={
            "steps": 3,
            "llm_calls": 2,
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "usd": 0.01,
            "browser_ms": 500,
        },
    )


def _observation_event(run_id: str = RUN_ID, seq: int = 1) -> ObservationEvent:
    return ObservationEvent(
        run_id=run_id,
        seq=seq,
        ts=TS,
        step_id="step-1",
        url="https://example.com",
        title="Example",
        ax_tree_digest="[button Submit]",
        ax_fingerprint="fp123",
        screenshot_ref="/tmp/shot.png",
        viewport={"w": 1280, "h": 800},
    )


def _plan_event(run_id: str = RUN_ID, seq: int = 1) -> PlanEvent:
    return PlanEvent(
        run_id=run_id,
        seq=seq,
        ts=TS,
        step_id="step-1",
        reason="initial",
        steps=["click the button", "verify result"],
        llm_call_id="llm-call-1",
    )


def _decision_event(run_id: str = RUN_ID, seq: int = 1) -> DecisionEvent:
    return DecisionEvent(
        run_id=run_id,
        seq=seq,
        ts=TS,
        step_id="step-1",
        intent="click the Submit button",
        tool="click",
        args={"selector": "#submit"},
        rationale="The submit button is visible.",
        llm_call_id="llm-call-1",
    )


def _locate_event(run_id: str = RUN_ID, seq: int = 1) -> LocateEvent:
    return LocateEvent(
        run_id=run_id,
        seq=seq,
        ts=TS,
        step_id="step-1",
        intent="click the Submit button",
        tier="L1_ax",
        outcome="hit",
        candidates=[
            {"ax_role": "button", "ax_name": "Submit", "selector": "#submit", "score": 0.9}
        ],
        chosen={"selector": "#submit", "ax_fingerprint": "fp123", "confidence": 0.9},
        cache_action="write",
        ms=42,
    )


def _act_event(run_id: str = RUN_ID, seq: int = 1) -> ActEvent:
    return ActEvent(
        run_id=run_id,
        seq=seq,
        ts=TS,
        step_id="step-1",
        tool="click",
        args={"selector": "#submit"},
        outcome="ok",
        diff={"url_changed": False, "ax_changed": True, "error": None},
        ms=100,
    )


def _supervisor_event(run_id: str = RUN_ID, seq: int = 1) -> SupervisorEvent:
    return SupervisorEvent(
        run_id=run_id,
        seq=seq,
        ts=TS,
        step_id="step-1",
        trigger_event_seq=3,
        classified_as="LocatorMiss",
        policy="next_tier",
        attempt=1,
    )


def _llm_call_event(run_id: str = RUN_ID, seq: int = 1) -> LLMCallEvent:
    return LLMCallEvent(
        run_id=run_id,
        seq=seq,
        ts=TS,
        step_id=None,
        llm_call_id="llm-call-1",
        purpose="decide",
        model="qwen3",
        base_url="http://localhost:8090",
        prompt={
            "system": "You are an agent.",
            "messages": [{"role": "user", "content": "What do you see?"}],
            "tools": None,
        },
        response={"content": "I see a form.", "tool_calls": None, "finish_reason": "stop"},
        tokens={"prompt": 50, "completion": 20},
        usd=0.001,
        ms=250,
    )


def _done_event(run_id: str = RUN_ID, seq: int = 1) -> DoneEvent:
    return DoneEvent(
        run_id=run_id,
        seq=seq,
        ts=TS,
        step_id="step-5",
        result={"answer": "cats"},
        evidence={
            "url": "https://example.com",
            "text_snippet": "cats",
            "screenshot_ref": None,
            "ax_path": None,
        },
        verifier={"ok": True, "reasons": ["result matches expected"]},
    )


# ---------------------------------------------------------------------------
# 1.1  Run round-trip
# ---------------------------------------------------------------------------


def test_run_round_trip():
    run = _run_full()
    json_str = run.model_dump_json()
    restored = Run.model_validate_json(json_str)
    assert restored == run


# ---------------------------------------------------------------------------
# 1.2  Run optional fields null
# ---------------------------------------------------------------------------


def test_run_optional_fields_null():
    run = Run(
        run_id=RUN_ID,
        task="do something",
        expect_schema=None,
        budget={"steps": 10, "usd": 0.5, "seconds": 60},
        llm={"base_url": "http://localhost", "model": "m", "temperature": 0.0, "seed": None},
        agent_version="v1",
        started_at=TS,
        ended_at=None,
        status=None,
        final=None,
        totals=None,
    )
    assert run.expect_schema is None
    assert run.ended_at is None
    assert run.status is None
    assert run.final is None
    assert run.totals is None
    data = json.loads(run.model_dump_json())
    assert data["expect_schema"] is None
    assert data["ended_at"] is None
    assert data["status"] is None
    assert data["final"] is None
    assert data["totals"] is None


# ---------------------------------------------------------------------------
# 1.3  Event round-trips
# ---------------------------------------------------------------------------


def test_observation_event_round_trip():
    ev = _observation_event()
    assert ObservationEvent.model_validate_json(ev.model_dump_json()) == ev


def test_plan_event_round_trip():
    ev = _plan_event()
    assert PlanEvent.model_validate_json(ev.model_dump_json()) == ev


def test_decision_event_round_trip():
    ev = _decision_event()
    assert DecisionEvent.model_validate_json(ev.model_dump_json()) == ev


def test_locate_event_round_trip():
    ev = _locate_event()
    assert LocateEvent.model_validate_json(ev.model_dump_json()) == ev


def test_act_event_round_trip():
    ev = _act_event()
    assert ActEvent.model_validate_json(ev.model_dump_json()) == ev


def test_supervisor_event_round_trip():
    ev = _supervisor_event()
    assert SupervisorEvent.model_validate_json(ev.model_dump_json()) == ev


def test_llm_call_event_round_trip():
    ev = _llm_call_event()
    assert LLMCallEvent.model_validate_json(ev.model_dump_json()) == ev


def test_done_event_round_trip():
    ev = _done_event()
    assert DoneEvent.model_validate_json(ev.model_dump_json()) == ev


# ---------------------------------------------------------------------------
# 1.4  LocateEvent with chosen=None
# ---------------------------------------------------------------------------


def test_locate_event_none_chosen():
    ev = LocateEvent(
        run_id=RUN_ID,
        seq=1,
        ts=TS,
        step_id=None,
        intent="find the button",
        tier="L1_ax",
        outcome="miss",
        candidates=[],
        chosen=None,
        cache_action=None,
        ms=10,
    )
    restored = LocateEvent.model_validate_json(ev.model_dump_json())
    assert restored == ev
    assert restored.chosen is None


# ---------------------------------------------------------------------------
# 1.5  AnyEvent discriminator
# ---------------------------------------------------------------------------


def test_any_event_discriminator():
    adapter = TypeAdapter(AnyEvent)
    obs = _observation_event()
    llm = _llm_call_event()
    done = _done_event()

    assert type(adapter.validate_json(obs.model_dump_json())) is ObservationEvent
    assert type(adapter.validate_json(llm.model_dump_json())) is LLMCallEvent
    assert type(adapter.validate_json(done.model_dump_json())) is DoneEvent


# ---------------------------------------------------------------------------
# 1.6  SeqError fields
# ---------------------------------------------------------------------------


def test_seq_error_fields():
    err = SeqError(expected_min=3, got=2)
    assert err.expected_min == 3
    assert err.got == 2


# ---------------------------------------------------------------------------
# 1.7  TraceWriter basic persist
# ---------------------------------------------------------------------------


def test_trace_writer_basic_persist():
    run = _run_full()
    ev = _observation_event(run_id=run.run_id, seq=1)
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        writer.append_event(ev)
        runs = list(writer._conn.execute("SELECT run_id FROM traces_runs"))
        events = list(
            writer._conn.execute("SELECT seq FROM traces_events WHERE run_id = ?", (run.run_id,))
        )
    assert len(runs) == 1
    assert runs[0][0] == run.run_id
    assert len(events) == 1
    assert events[0][0] == 1


# ---------------------------------------------------------------------------
# 1.8  TraceWriter rejects duplicate seq
# ---------------------------------------------------------------------------


def test_trace_writer_rejects_duplicate_seq():
    run = _run_full()
    ev1 = _observation_event(run_id=run.run_id, seq=1)
    ev2 = _observation_event(run_id=run.run_id, seq=1)
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        writer.append_event(ev1)
        with pytest.raises(SeqError):
            writer.append_event(ev2)


# ---------------------------------------------------------------------------
# 1.9  TraceWriter rejects out-of-order seq
# ---------------------------------------------------------------------------


def test_trace_writer_rejects_out_of_order_seq():
    run = _run_full()
    ev5 = _observation_event(run_id=run.run_id, seq=5)
    ev3 = _observation_event(run_id=run.run_id, seq=3)
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        writer.append_event(ev5)
        with pytest.raises(SeqError):
            writer.append_event(ev3)


# ---------------------------------------------------------------------------
# 1.10  TraceWriter accepts increasing seq
# ---------------------------------------------------------------------------


def test_trace_writer_accepts_increasing_seq():
    run = _run_full()
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        writer.append_event(_observation_event(run_id=run.run_id, seq=1))
        writer.append_event(_observation_event(run_id=run.run_id, seq=2))
        writer.append_event(_observation_event(run_id=run.run_id, seq=3))
        rows = list(
            writer._conn.execute("SELECT seq FROM traces_events WHERE run_id = ?", (run.run_id,))
        )
    assert len(rows) == 3


# ---------------------------------------------------------------------------
# 1.11  redact strips Authorization header
# ---------------------------------------------------------------------------


def test_redact_authorization_header():
    ev = LLMCallEvent(
        run_id=RUN_ID,
        seq=1,
        ts=TS,
        step_id=None,
        llm_call_id="llm-1",
        purpose="decide",
        model="qwen3",
        base_url="http://localhost:8090",
        prompt={
            "system": None,
            "messages": [{"role": "tool", "content": "Authorization: Bearer secret-token"}],
            "tools": None,
        },
        response={"content": "ok", "tool_calls": None, "finish_reason": "stop"},
        tokens={"prompt": 10, "completion": 5},
        usd=0.0,
        ms=10,
    )
    redacted = redact(ev)
    content = redacted.prompt["messages"][0]["content"]
    assert "[REDACTED]" in content
    assert "secret-token" not in content
    # original unchanged
    assert ev.prompt["messages"][0]["content"] == "Authorization: Bearer secret-token"


# ---------------------------------------------------------------------------
# 1.12  redact type tool text
# ---------------------------------------------------------------------------


def test_redact_type_tool_text():
    ev = DecisionEvent(
        run_id=RUN_ID,
        seq=1,
        ts=TS,
        step_id=None,
        intent="password field",
        tool="type",
        args={"intent": "password field", "text": "MyP@ssw0rd"},
        rationale="filling password",
        llm_call_id="llm-1",
    )
    redacted = redact(ev)
    assert redacted.args["text"] == "[REDACTED]"
    assert ev.args["text"] == "MyP@ssw0rd"


# ---------------------------------------------------------------------------
# 1.13  redact noop for ObservationEvent
# ---------------------------------------------------------------------------


def test_redact_noop_for_observation():
    ev = _observation_event()
    result = redact(ev)
    assert result == ev


# ---------------------------------------------------------------------------
# 1.14  TraceWriter redacts before persist
# ---------------------------------------------------------------------------


def test_trace_writer_redacts_before_persist():
    run = _run_full()
    ev = LLMCallEvent(
        run_id=run.run_id,
        seq=1,
        ts=TS,
        step_id=None,
        llm_call_id="llm-1",
        purpose="decide",
        model="qwen3",
        base_url="http://localhost:8090",
        prompt={
            "system": None,
            "messages": [{"role": "tool", "content": "Authorization: Bearer secret"}],
            "tools": None,
        },
        response={"content": "ok", "tool_calls": None, "finish_reason": "stop"},
        tokens={"prompt": 10, "completion": 5},
        usd=0.0,
        ms=10,
    )
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        writer.append_event(ev)
        row = writer._conn.execute(
            "SELECT payload FROM traces_events WHERE run_id = ? AND seq = 1", (run.run_id,)
        ).fetchone()
    payload = row[0]
    assert "secret" not in payload
    assert "[REDACTED]" in payload


# ---------------------------------------------------------------------------
# 5.3  Context manager closes connection on both normal and exception exit
# ---------------------------------------------------------------------------


def test_trace_writer_context_manager_normal_exit():
    writer = TraceWriter(":memory:")
    with writer:
        pass
    assert writer._conn is None


def test_trace_writer_context_manager_exception_exit():
    writer = TraceWriter(":memory:")
    with pytest.raises(RuntimeError):
        with writer:
            raise RuntimeError("boom")
    assert writer._conn is None
