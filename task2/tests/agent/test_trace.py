"""Tests for agent.trace module."""

from __future__ import annotations

import json
import sqlite3

import pytest
from pydantic import TypeAdapter, ValidationError

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

RUN_ID = "01HZXYZ0000000000000000000"
TS = "2024-01-01T00:00:00Z"


def _run_full() -> Run:
    """A freshly opened run: terminal fields are None until close_run is called."""
    return Run(
        run_id=RUN_ID,
        task="search for cats",
        expect_schema={"type": "object"},
        budget={"steps": 20, "usd": 1.0, "seconds": 300},
        llm={"base_url": "http://localhost:8090", "model": "qwen3", "temperature": 0.0, "seed": 42},
        agent_version="abc123",
        started_at=TS,
        ended_at=None,
        status=None,
        final=None,
        totals=None,
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


def _llm_call_event(
    run_id: str = RUN_ID,
    seq: int = 1,
    messages: list[dict[str, object]] | None = None,
) -> LLMCallEvent:
    if messages is None:
        messages = [{"role": "user", "content": "What do you see?"}]
    return LLMCallEvent(
        run_id=run_id,
        seq=seq,
        ts=TS,
        step_id=None,
        llm_call_id="llm-call-1",
        purpose="decide",
        model="qwen3",
        base_url="http://localhost:8090",
        prompt={"system": "You are an agent.", "messages": messages, "tools": None},
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


def test_run_round_trip():
    run = _run_full()
    json_str = run.model_dump_json()
    restored = Run.model_validate_json(json_str)
    assert restored == run


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
    data = json.loads(run.model_dump_json())
    assert data["expect_schema"] is None
    assert data["ended_at"] is None
    assert data["status"] is None
    assert data["final"] is None
    assert data["totals"] is None


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


def test_any_event_discriminator():
    adapter = TypeAdapter(AnyEvent)
    obs = _observation_event()
    llm = _llm_call_event()
    done = _done_event()

    assert type(adapter.validate_json(obs.model_dump_json())) is ObservationEvent
    assert type(adapter.validate_json(llm.model_dump_json())) is LLMCallEvent
    assert type(adapter.validate_json(done.model_dump_json())) is DoneEvent


def test_seq_error_fields():
    err = SeqError(expected_min=3, got=2)
    assert err.expected_min == 3
    assert err.got == 2


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


def test_trace_writer_rejects_duplicate_seq():
    run = _run_full()
    ev1 = _observation_event(run_id=run.run_id, seq=1)
    ev2 = _observation_event(run_id=run.run_id, seq=1)
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        writer.append_event(ev1)
        with pytest.raises(SeqError):
            writer.append_event(ev2)


def test_trace_writer_rejects_out_of_order_seq():
    run = _run_full()
    ev5 = _observation_event(run_id=run.run_id, seq=5)
    ev3 = _observation_event(run_id=run.run_id, seq=3)
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        writer.append_event(ev5)
        with pytest.raises(SeqError):
            writer.append_event(ev3)


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


def test_redact_authorization_header():
    ev = _llm_call_event(
        messages=[{"role": "tool", "content": "Authorization: Bearer secret-token"}],
    )
    redacted = redact(ev)
    content = redacted.prompt["messages"][0]["content"]
    assert "[REDACTED]" in content
    assert "secret-token" not in content
    assert ev.prompt["messages"][0]["content"] == "Authorization: Bearer secret-token"


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


def test_redact_noop_for_observation():
    ev = _observation_event()
    result = redact(ev)
    assert result == ev


def test_trace_writer_redacts_before_persist():
    run = _run_full()
    ev = _llm_call_event(
        run_id=run.run_id,
        messages=[{"role": "tool", "content": "Authorization: Bearer secret"}],
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


def test_trace_writer_close_run_persists_fields():
    run = _run_full()
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        writer.close_run(
            run.run_id,
            status="succeeded",
            ended_at="2024-01-01T00:01:00Z",
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
        row = writer._conn.execute(
            "SELECT status, ended_at, final_json, totals_json FROM traces_runs WHERE run_id = ?",
            (run.run_id,),
        ).fetchone()
    assert row is not None
    assert row[0] == "succeeded"
    assert row[1] == "2024-01-01T00:01:00Z"
    assert json.loads(row[2]) == {"result": {"answer": "cats"}, "evidence": {}, "failure": None}
    assert json.loads(row[3])["steps"] == 3


def test_trace_writer_open_run_duplicate_raises():
    run = _run_full()
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        with pytest.raises(sqlite3.IntegrityError):
            writer.open_run(run)


def test_redact_mixed_messages_only_dirty_redacted():
    ev = _llm_call_event(
        messages=[
            {"role": "user", "content": "What do you see?"},
            {"role": "tool", "content": "Authorization: Bearer secret-token"},
        ],
    )
    redacted = redact(ev)
    msgs = redacted.prompt["messages"]
    assert msgs[0]["content"] == "What do you see?"
    assert "[REDACTED]" in msgs[1]["content"]
    assert "secret-token" not in msgs[1]["content"]


def test_trace_writer_close_idempotent():
    writer = TraceWriter(":memory:")
    writer.close()
    assert writer._conn is None
    writer.close()
    assert writer._conn is None


def test_redact_act_event_type_text():
    """ActEvent recording an executed type action must also have args['text'] redacted."""
    ev = ActEvent(
        run_id=RUN_ID,
        seq=1,
        ts=TS,
        step_id=None,
        tool="type",
        args={"intent": "password field", "text": "MyP@ssw0rd"},
        outcome="ok",
        diff={"url_changed": False, "ax_changed": True, "error": None},
        ms=10,
    )
    redacted = redact(ev)
    assert redacted.args["text"] == "[REDACTED]"
    assert ev.args["text"] == "MyP@ssw0rd"


def test_trace_writer_redacts_act_event_before_persist():
    run = _run_full()
    ev = ActEvent(
        run_id=run.run_id,
        seq=1,
        ts=TS,
        step_id=None,
        tool="type",
        args={"intent": "password field", "text": "supersecret"},
        outcome="ok",
        diff={"url_changed": False, "ax_changed": True, "error": None},
        ms=10,
    )
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        writer.append_event(ev)
        row = writer._conn.execute(
            "SELECT payload FROM traces_events WHERE run_id = ? AND seq = 1", (run.run_id,)
        ).fetchone()
    payload = row[0]
    assert "supersecret" not in payload
    assert "[REDACTED]" in payload


def test_append_event_rejects_unknown_run_id():
    """append_event must fail fast if run_id is not in traces_runs."""
    ev = _observation_event(run_id="never-opened", seq=1)
    with TraceWriter(":memory:") as writer:
        with pytest.raises(LookupError):
            writer.append_event(ev)


def test_close_run_refreshes_payload_blob():
    """close_run must rewrite payload so the canonical Run JSON reflects final state."""
    run = _run_full()
    initial = Run(
        run_id=run.run_id,
        task=run.task,
        expect_schema=run.expect_schema,
        budget=run.budget,
        llm=run.llm,
        agent_version=run.agent_version,
        started_at=run.started_at,
        ended_at=None,
        status=None,
        final=None,
        totals=None,
    )
    with TraceWriter(":memory:") as writer:
        writer.open_run(initial)
        writer.close_run(
            initial.run_id,
            status="succeeded",
            ended_at="2024-01-01T00:01:00Z",
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
        row = writer._conn.execute(
            "SELECT payload FROM traces_runs WHERE run_id = ?", (initial.run_id,)
        ).fetchone()
    payload = json.loads(row[0])
    assert payload["status"] == "succeeded"
    assert payload["ended_at"] == "2024-01-01T00:01:00Z"
    assert payload["final"]["result"] == {"answer": "cats"}
    assert payload["totals"]["steps"] == 3


def test_close_run_rejects_invalid_status():
    """close_run must validate the merged Run so invalid status doesn't poison payload."""
    run = _run_full()
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        with pytest.raises(ValidationError):
            writer.close_run(
                run.run_id,
                status="success",
                ended_at=TS,
                final={},
                totals={},
            )
        row = writer._conn.execute(
            "SELECT payload FROM traces_runs WHERE run_id = ?", (run.run_id,)
        ).fetchone()
    payload = json.loads(row[0])
    assert payload["status"] is None


def test_close_run_rejects_double_close():
    """close_run must refuse to rewrite an already-closed run."""
    run = _run_full()
    closing_args = {
        "ended_at": "2024-01-01T00:01:00Z",
        "final": {"result": {"answer": "cats"}, "evidence": None, "failure": None},
        "totals": {
            "steps": 1,
            "llm_calls": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "usd": 0.0,
            "browser_ms": 0,
        },
    }
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        writer.close_run(run.run_id, status="succeeded", **closing_args)
        with pytest.raises(ValueError):
            writer.close_run(run.run_id, status="failed", **closing_args)
        row = writer._conn.execute(
            "SELECT status FROM traces_runs WHERE run_id = ?", (run.run_id,)
        ).fetchone()
    assert row[0] == "succeeded"


def test_close_run_normalizes_helper_columns():
    """close_run must persist helper columns from the validated Run, not raw inputs."""
    run = _run_full()
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        writer.close_run(
            run.run_id,
            status="succeeded",
            ended_at="2024-01-01T00:01:00Z",
            final={"result": {"answer": "cats"}, "evidence": None, "failure": None},
            totals={
                "steps": "3",  # coercible string -> int
                "llm_calls": 2,
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "usd": 0.01,
                "browser_ms": 500,
            },
        )
        row = writer._conn.execute(
            "SELECT payload, totals_json FROM traces_runs WHERE run_id = ?", (run.run_id,)
        ).fetchone()
    payload_totals = json.loads(row[0])["totals"]
    totals_json = json.loads(row[1])
    assert payload_totals["steps"] == 3
    assert totals_json["steps"] == 3
    assert totals_json == payload_totals


def test_close_run_unknown_run_id_raises():
    with TraceWriter(":memory:") as writer:
        with pytest.raises(LookupError):
            writer.close_run("does-not-exist", status="failed", ended_at=TS, final={}, totals={})


def test_run_budget_rejects_missing_key():
    """Budget must be a typed submodel — missing keys must fail validation."""
    with pytest.raises(ValidationError):
        Run(
            run_id=RUN_ID,
            task="t",
            expect_schema=None,
            budget={"steps": 10, "usd": 0.5},  # missing 'seconds'
            llm={"base_url": "x", "model": "m", "temperature": 0.0, "seed": None},
            agent_version="v1",
            started_at=TS,
            ended_at=None,
            status=None,
            final=None,
            totals=None,
        )


def test_run_totals_rejects_wrong_type():
    """Totals must be a typed submodel — wrong types must fail validation."""
    with pytest.raises(ValidationError):
        Run(
            run_id=RUN_ID,
            task="t",
            expect_schema=None,
            budget={"steps": 10, "usd": 0.5, "seconds": 60},
            llm={"base_url": "x", "model": "m", "temperature": 0.0, "seed": None},
            agent_version="v1",
            started_at=TS,
            ended_at=TS,
            status="succeeded",
            final={"result": None, "evidence": None, "failure": None},
            totals={
                "steps": "three",  # should be int
                "llm_calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "usd": 0.0,
                "browser_ms": 0,
            },
        )


def test_open_run_rejects_run_with_terminal_status():
    """open_run must refuse a Run whose payload already has a terminal status."""
    closed_run = _run_full().model_copy(
        update={
            "status": "succeeded",
            "ended_at": "2024-01-01T00:01:00Z",
            "final": {"result": {"answer": "cats"}, "evidence": None, "failure": None},
            "totals": {
                "steps": 1,
                "llm_calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "usd": 0.0,
                "browser_ms": 0,
            },
        }
    )
    with TraceWriter(":memory:") as writer:
        with pytest.raises(ValueError):
            writer.open_run(closed_run)


def test_append_event_rejects_after_close_run():
    """append_event must fail fast once close_run has set terminal state."""
    run = _run_full()
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        writer.append_event(_observation_event(run_id=run.run_id, seq=1))
        writer.close_run(
            run.run_id,
            status="succeeded",
            ended_at="2024-01-01T00:01:00Z",
            final={"result": {"answer": "cats"}, "evidence": {}, "failure": None},
            totals={
                "steps": 1,
                "llm_calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "usd": 0.0,
                "browser_ms": 0,
            },
        )
        with pytest.raises(LookupError):
            writer.append_event(_observation_event(run_id=run.run_id, seq=2))


def test_observation_event_last_actions_default_empty():
    event = _observation_event()
    assert event.last_actions == []
    data = json.loads(event.model_dump_json())
    assert data["last_actions"] == []


def test_observation_event_last_actions_round_trip():
    action = {"tool": "goto", "intent": "x", "outcome": "ok"}
    event = ObservationEvent(
        run_id=RUN_ID,
        seq=1,
        ts=TS,
        step_id="step-1",
        url="https://example.com",
        title="Example",
        ax_tree_digest="[button Submit]",
        ax_fingerprint="fp123",
        screenshot_ref="/tmp/shot.png",
        viewport={"w": 1280, "h": 800},
        last_actions=[action],
    )
    restored = ObservationEvent.model_validate_json(event.model_dump_json())
    assert restored.last_actions == [action]


def test_observation_event_error_entry_round_trip():
    action = {"tool": "goto", "intent": "x", "outcome": "error", "error": "bad url"}
    event = ObservationEvent(
        run_id=RUN_ID,
        seq=1,
        ts=TS,
        step_id="step-1",
        url="https://example.com",
        title="Example",
        ax_tree_digest="[button Submit]",
        ax_fingerprint="fp123",
        screenshot_ref="/tmp/shot.png",
        viewport={"w": 1280, "h": 800},
        last_actions=[action],
    )
    restored = ObservationEvent.model_validate_json(event.model_dump_json())
    assert "error" in restored.last_actions[0]
    assert restored.last_actions[0]["error"] == "bad url"


def test_redact_handles_non_dict_messages():
    """redact must not crash when prompt['messages'] entries aren't dicts."""
    ev = _llm_call_event(messages=["a bare string", {"role": "user", "content": "ok"}])
    redacted = redact(ev)
    msgs = redacted.prompt["messages"]
    assert msgs[0] == "a bare string"
    assert msgs[1]["content"] == "ok"


def test_trace_writer_methods_on_closed_raise():
    writer = TraceWriter(":memory:")
    writer.close()
    with pytest.raises(sqlite3.ProgrammingError):
        writer.open_run(_run_full())
    with pytest.raises(sqlite3.ProgrammingError):
        writer.append_event(_observation_event())
    with pytest.raises(sqlite3.ProgrammingError):
        writer.close_run("x", status="failed", ended_at=TS, final={}, totals={})
    with pytest.raises(sqlite3.ProgrammingError):
        writer.next_seq("any-run-id")


def test_next_seq_on_fresh_run_returns_1():
    run = _run_full()
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        assert writer.next_seq(run.run_id) == 1


def test_next_seq_after_one_event_returns_2():
    run = _run_full()
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        writer.append_event(_observation_event(run_id=run.run_id, seq=1))
        assert writer.next_seq(run.run_id) == 2


def test_next_seq_after_three_events_returns_4():
    run = _run_full()
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        writer.append_event(_observation_event(run_id=run.run_id, seq=1))
        writer.append_event(_observation_event(run_id=run.run_id, seq=2))
        writer.append_event(_observation_event(run_id=run.run_id, seq=3))
        assert writer.next_seq(run.run_id) == 4


def test_next_seq_unknown_run_id_raises():
    with TraceWriter(":memory:") as writer:
        with pytest.raises(LookupError):
            writer.next_seq("does-not-exist")


def test_next_seq_closed_run_raises():
    run = _run_full()
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        writer.close_run(
            run.run_id,
            status="succeeded",
            ended_at="2024-01-01T00:01:00Z",
            final={"result": {"answer": "cats"}, "evidence": {}, "failure": None},
            totals={
                "steps": 1,
                "llm_calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "usd": 0.0,
                "browser_ms": 0,
            },
        )
        with pytest.raises(LookupError):
            writer.next_seq(run.run_id)


def test_iter_events_empty_run_returns_empty_iterator():
    run = _run_full()
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        assert list(writer.iter_events(run.run_id)) == []


def test_iter_events_unknown_run_id_returns_empty_iterator():
    with TraceWriter(":memory:") as writer:
        assert list(writer.iter_events("never-opened-run")) == []


def test_iter_events_yields_n_events_in_seq_order():
    run = _run_full()
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        writer.append_event(_plan_event(run_id=run.run_id, seq=1))
        writer.append_event(_locate_event(run_id=run.run_id, seq=2))
        writer.append_event(_supervisor_event(run_id=run.run_id, seq=3))
        result = list(writer.iter_events(run.run_id))
    assert len(result) == 3
    assert isinstance(result[0], PlanEvent)
    assert result[0].seq == 1
    assert isinstance(result[1], LocateEvent)
    assert result[1].seq == 2
    assert isinstance(result[2], SupervisorEvent)
    assert result[2].seq == 3


def test_iter_events_types_match_any_event_adapter():
    from agent.trace import _any_event_adapter

    run = _run_full()
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        writer.append_event(_plan_event(run_id=run.run_id, seq=1))
        writer.append_event(_locate_event(run_id=run.run_id, seq=2))
        writer.append_event(_supervisor_event(run_id=run.run_id, seq=3))
        result = list(writer.iter_events(run.run_id))
        raw_rows = writer._conn.execute(
            "SELECT payload FROM traces_events WHERE run_id = ? ORDER BY seq", (run.run_id,)
        ).fetchall()
    expected = [_any_event_adapter.validate_json(row[0]) for row in raw_rows]
    assert result == expected


def test_iter_events_on_closed_writer_raises():
    writer = TraceWriter(":memory:")
    writer.close()
    with pytest.raises(sqlite3.ProgrammingError):
        list(writer.iter_events("any-run-id"))


def test_iter_events_on_closed_run_still_yields():
    run = _run_full()
    with TraceWriter(":memory:") as writer:
        writer.open_run(run)
        writer.append_event(_plan_event(run_id=run.run_id, seq=1))
        writer.append_event(_locate_event(run_id=run.run_id, seq=2))
        writer.close_run(
            run.run_id,
            status="succeeded",
            ended_at="2024-01-01T00:01:00Z",
            final={"result": {"answer": "cats"}, "evidence": {}, "failure": None},
            totals={
                "steps": 1,
                "llm_calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "usd": 0.0,
                "browser_ms": 0,
            },
        )
        result = list(writer.iter_events(run.run_id))
    assert len(result) == 2
