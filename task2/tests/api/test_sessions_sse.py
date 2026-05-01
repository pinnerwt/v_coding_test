from __future__ import annotations

import json
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from agent.loop import RunResult


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:9999")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    return db_path


@pytest.fixture
def client(temp_db):
    from api.server import app
    from api.sessions import _SESSIONS

    with patch.dict(_SESSIONS, {}, clear=True):
        yield TestClient(app)


def _wait_for(predicate, timeout: float = 2.0, interval: float = 0.01) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False


_DONE_RESULT = RunResult(
    status="succeeded",
    result={"ok": True},
    evidence={"url": "http://x", "text_snippet": "x"},
)


def _parse_sse(stream_iter, *, max_events: int = 20):
    events = []
    buffer = ""
    for chunk in stream_iter:
        if isinstance(chunk, bytes):
            chunk = chunk.decode("utf-8")
        buffer += chunk
        while "\n\n" in buffer:
            frame, buffer = buffer.split("\n\n", 1)
            for line in frame.splitlines():
                if line.startswith("data: "):
                    events.append(json.loads(line[len("data: ") :]))
            if len(events) >= max_events:
                return events
    return events


def test_sse_stream_emits_terminal_for_simple_run(client, monkeypatch):
    monkeypatch.setattr("api.sessions._invoke_loop", lambda *a, **kw: _DONE_RESULT)
    run_id = client.post("/sessions", json={"task": "ok"}).json()["id"]

    from api.sessions import get_session

    assert _wait_for(lambda: get_session(run_id).status == "done")

    with client.stream("GET", f"/sessions/{run_id}/events") as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(resp.iter_text(), max_events=10)

    types = [e.get("type") for e in events]
    assert "terminal" in types
    terminal = next(e for e in events if e["type"] == "terminal")
    assert terminal["status"] == "done"


def test_sse_stream_emits_ask_user_and_answer(client, monkeypatch):
    def fake_loop(task, *, ask_user_callback, **kw):
        ans = ask_user_callback("which one?")
        return RunResult(
            status="succeeded",
            result={"got": ans},
            evidence={"url": "x", "text_snippet": "x"},
        )

    monkeypatch.setattr("api.sessions._invoke_loop", fake_loop)
    run_id = client.post("/sessions", json={"task": "ambiguous"}).json()["id"]

    from api.sessions import get_session

    assert _wait_for(lambda: get_session(run_id).status == "awaiting_user")
    client.post(f"/sessions/{run_id}/answer", json={"answer": "B"})
    assert _wait_for(lambda: get_session(run_id).status == "done")

    with client.stream("GET", f"/sessions/{run_id}/events") as resp:
        events = _parse_sse(resp.iter_text(), max_events=20)

    types = [e.get("type") for e in events]
    assert "ask_user" in types
    assert "answer" in types
    ask = next(e for e in events if e["type"] == "ask_user")
    assert ask["question"] == "which one?"
    ans = next(e for e in events if e["type"] == "answer")
    assert ans["answer"] == "B"


def test_sse_stream_404_for_unknown_session(client):
    resp = client.get("/sessions/nonexistent/events")
    assert resp.status_code == 404


def test_post_sessions_forwards_locale_to_loop(client, monkeypatch):
    """POST /sessions {task, locale} must reach loop() with locale=<value>."""
    captured: dict = {}

    def fake_loop(task, *, locale=None, **kw):
        captured["locale"] = locale
        return _DONE_RESULT

    monkeypatch.setattr("api.sessions._invoke_loop", fake_loop)
    resp = client.post("/sessions", json={"task": "hi", "locale": "zh-TW"})
    assert resp.status_code == 200
    run_id = resp.json()["id"]

    from api.sessions import get_session

    assert _wait_for(lambda: get_session(run_id).status == "done")
    assert captured.get("locale") == "zh-TW"


def test_chat_html_posts_navigator_language_as_locale(client):
    """The chat UI must include locale=navigator.language in the /sessions
    POST body so the planner is anchored to the user's region."""
    resp = client.get("/chat")
    assert resp.status_code == 200
    body = resp.text
    assert "navigator.language" in body
    assert "locale" in body


def test_terminal_event_forwards_failed_status_and_reason(client, monkeypatch):
    """When loop returns RunResult(status='failed', reason='stuck_repeat'),
    the SSE terminal event must reflect that — not lie with status='done'."""
    monkeypatch.setattr(
        "api.sessions._invoke_loop",
        lambda *a, **kw: RunResult(
            status="failed",
            reason="stuck_repeat",
            result=None,
            evidence=None,
        ),
    )
    run_id = client.post("/sessions", json={"task": "t"}).json()["id"]

    from api.sessions import get_session

    assert _wait_for(lambda: get_session(run_id).status in ("done", "failed"))

    with client.stream("GET", f"/sessions/{run_id}/events") as resp:
        events = _parse_sse(resp.iter_text(), max_events=10)

    terminal = next(e for e in events if e["type"] == "terminal")
    assert terminal["status"] == "failed", f"got {terminal!r}"
    assert terminal.get("reason") == "stuck_repeat", f"got {terminal!r}"


def test_terminal_event_forwards_timeout_status(client, monkeypatch):
    monkeypatch.setattr(
        "api.sessions._invoke_loop",
        lambda *a, **kw: RunResult(
            status="timeout",
            reason="seconds_budget",
            result=None,
            evidence=None,
        ),
    )
    run_id = client.post("/sessions", json={"task": "t"}).json()["id"]

    from api.sessions import get_session

    assert _wait_for(lambda: get_session(run_id).status in ("done", "failed"))

    with client.stream("GET", f"/sessions/{run_id}/events") as resp:
        events = _parse_sse(resp.iter_text(), max_events=10)

    terminal = next(e for e in events if e["type"] == "terminal")
    assert terminal["status"] == "timeout"
    assert terminal.get("reason") == "seconds_budget"


def test_post_sessions_locale_optional(client, monkeypatch):
    """Locale is optional; omitting it must not break session creation."""
    captured: dict = {}

    def fake_loop(task, *, locale=None, **kw):
        captured["locale"] = locale
        return _DONE_RESULT

    monkeypatch.setattr("api.sessions._invoke_loop", fake_loop)
    resp = client.post("/sessions", json={"task": "hi"})
    assert resp.status_code == 200

    from api.sessions import get_session

    run_id = resp.json()["id"]
    assert _wait_for(lambda: get_session(run_id).status == "done")
    assert captured.get("locale") is None


def test_streaming_trace_writer_calls_on_event(tmp_path):
    from agent.trace import ActEvent, Run, RunBudget, RunLLM
    from api.streaming_trace import StreamingTraceWriter

    captured: list[dict] = []
    writer = StreamingTraceWriter(str(tmp_path / "t.db"), on_event=captured.append)
    run = Run(
        run_id="r1",
        task="t",
        expect_schema=None,
        budget=RunBudget(steps=1, usd=1.0, seconds=1),
        llm=RunLLM(base_url="x", model="y", temperature=0.0, seed=None),
        agent_version="0.0",
        started_at="2025-01-01T00:00:00Z",
        ended_at=None,
        status=None,
        final=None,
        totals=None,
    )
    writer.open_run(run)
    event = ActEvent(
        run_id="r1",
        seq=1,
        ts="2025-01-01T00:00:01Z",
        step_id="s1",
        tool="goto",
        args={"url": "http://x"},
        outcome="ok",
        diff={},
        ms=10,
    )
    writer.append_event(event)
    writer.close()

    assert len(captured) == 1
    assert captured[0]["kind"] == "act"
    assert captured[0]["tool"] == "goto"


def test_streaming_trace_writer_swallows_subscriber_errors(tmp_path):
    from agent.trace import ActEvent, Run, RunBudget, RunLLM
    from api.streaming_trace import StreamingTraceWriter

    def boom(_):
        raise RuntimeError("subscriber crashed")

    writer = StreamingTraceWriter(str(tmp_path / "t.db"), on_event=boom)
    run = Run(
        run_id="r2",
        task="t",
        expect_schema=None,
        budget=RunBudget(steps=1, usd=1.0, seconds=1),
        llm=RunLLM(base_url="x", model="y", temperature=0.0, seed=None),
        agent_version="0.0",
        started_at="2025-01-01T00:00:00Z",
        ended_at=None,
        status=None,
        final=None,
        totals=None,
    )
    writer.open_run(run)
    event = ActEvent(
        run_id="r2",
        seq=1,
        ts="2025-01-01T00:00:01Z",
        step_id="s1",
        tool="goto",
        args={},
        outcome="ok",
        diff={},
        ms=10,
    )
    writer.append_event(event)
    writer.close()
    # Verify event was still persisted
    from agent.trace import TraceWriter

    reader = TraceWriter(str(tmp_path / "t.db"))
    try:
        events = list(reader.iter_events("r2"))
    finally:
        reader.close()
    assert len(events) == 1
