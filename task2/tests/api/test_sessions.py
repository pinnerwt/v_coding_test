from __future__ import annotations

import time
from typing import Any
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


def _wait_for(predicate, timeout: float = 2.0, interval: float = 0.02) -> bool:
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


def test_session_state_defaults():
    from api.sessions import SessionState

    s = SessionState(run_id="abc")
    assert s.run_id == "abc"
    assert s.status == "running"
    assert s.pending_question is None
    assert s.answer_queue.empty()
    assert s.result is None


def test_post_sessions_returns_id_and_registers(client, monkeypatch):
    monkeypatch.setattr("api.sessions._invoke_loop", lambda *a, **kw: _DONE_RESULT)

    resp = client.post("/sessions", json={"task": "do a thing"})

    assert resp.status_code == 200
    body = resp.json()
    assert "id" in body
    run_id = body["id"]
    from api.sessions import get_session

    assert _wait_for(lambda: get_session(run_id) is not None)


def test_session_reaches_done_when_loop_returns(client, monkeypatch):
    monkeypatch.setattr("api.sessions._invoke_loop", lambda *a, **kw: _DONE_RESULT)
    resp = client.post("/sessions", json={"task": "do a thing"})
    run_id = resp.json()["id"]

    from api.sessions import get_session

    assert _wait_for(lambda: get_session(run_id).status == "done")
    sess = get_session(run_id)
    assert sess.result is not None
    assert sess.result.status == "succeeded"


def test_get_session_returns_status(client, monkeypatch):
    monkeypatch.setattr("api.sessions._invoke_loop", lambda *a, **kw: _DONE_RESULT)
    run_id = client.post("/sessions", json={"task": "do a thing"}).json()["id"]

    from api.sessions import get_session

    _wait_for(lambda: get_session(run_id).status == "done")
    resp = client.get(f"/sessions/{run_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done"
    assert body["pending_question"] is None
    assert body["result"] == {"ok": True}


def test_session_ask_user_round_trip(client, monkeypatch):
    captured_answer: dict[str, Any] = {}

    def fake_loop(task: str, *, ask_user_callback, **kw) -> RunResult:
        answer = ask_user_callback("which branch?")
        captured_answer["value"] = answer
        return _DONE_RESULT

    monkeypatch.setattr("api.sessions._invoke_loop", fake_loop)

    run_id = client.post("/sessions", json={"task": "ambiguous"}).json()["id"]

    from api.sessions import get_session

    assert _wait_for(lambda: get_session(run_id).status == "awaiting_user")
    assert get_session(run_id).pending_question == "which branch?"

    resp = client.get(f"/sessions/{run_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "awaiting_user"
    assert resp.json()["pending_question"] == "which branch?"

    resp = client.post(f"/sessions/{run_id}/answer", json={"answer": "Tianmu"})
    assert resp.status_code == 200

    assert _wait_for(lambda: get_session(run_id).status == "done")
    assert captured_answer["value"] == "Tianmu"


def test_post_answer_when_not_awaiting_returns_409(client, monkeypatch):
    monkeypatch.setattr("api.sessions._invoke_loop", lambda *a, **kw: _DONE_RESULT)
    run_id = client.post("/sessions", json={"task": "do a thing"}).json()["id"]

    from api.sessions import get_session

    _wait_for(lambda: get_session(run_id).status == "done")
    resp = client.post(f"/sessions/{run_id}/answer", json={"answer": "x"})
    assert resp.status_code == 409


def test_get_session_unknown_returns_404(client):
    resp = client.get("/sessions/nonexistent")
    assert resp.status_code == 404


def test_post_answer_unknown_session_returns_404(client):
    resp = client.post("/sessions/nonexistent/answer", json={"answer": "x"})
    assert resp.status_code == 404


def test_post_sessions_empty_task_returns_422(client):
    resp = client.post("/sessions", json={"task": ""})
    assert resp.status_code == 422


def test_post_answer_empty_returns_422(client, monkeypatch):
    monkeypatch.setattr("api.sessions._invoke_loop", lambda *a, **kw: _DONE_RESULT)
    run_id = client.post("/sessions", json={"task": "ok"}).json()["id"]
    resp = client.post(f"/sessions/{run_id}/answer", json={"answer": ""})
    assert resp.status_code == 422


def test_session_failed_status_when_loop_raises(client, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("simulated agent crash")

    monkeypatch.setattr("api.sessions._invoke_loop", boom)
    run_id = client.post("/sessions", json={"task": "do a thing"}).json()["id"]

    from api.sessions import get_session

    assert _wait_for(lambda: get_session(run_id).status == "failed")


def test_invoke_loop_plumbs_run_budget_seconds_and_steps_to_loop(temp_db, monkeypatch):
    """I3: _invoke_loop must pass RunBudget.seconds and RunBudget.steps through
    to loop() as budget_seconds / max_steps. Without this, loop() never honors
    the wall-clock budget, runs until max_steps default exhaustion, and the
    runner's harness times out before terminal SSE fires (round-10 A1)."""
    captured: dict = {}

    def fake_loop(task, browser, llm_client, **kw):
        captured.update(kw)
        return _DONE_RESULT

    class _NoopCM:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("api.sessions.loop", fake_loop)
    monkeypatch.setattr("api.sessions.Browser", lambda *a, **kw: _NoopCM())
    monkeypatch.setattr("api.sessions.LLMClient", lambda *a, **kw: _NoopCM())

    from api.sessions import _invoke_loop

    _invoke_loop(
        task="t",
        run_id="r-i3",
        expect_schema=None,
        ask_user_callback=lambda q: "x",
    )

    assert captured.get("budget_seconds") == 300, (
        f"budget_seconds must be plumbed from RunBudget; got {captured!r}"
    )
    assert captured.get("max_steps") == 20, (
        f"max_steps must be plumbed from RunBudget; got {captured!r}"
    )
