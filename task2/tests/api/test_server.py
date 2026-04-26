from __future__ import annotations

import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from agent.loop import RunResult
from agent.trace import (
    DoneEvent,
    ObservationEvent,
    Run,
    RunBudget,
    RunLLM,
    TraceWriter,
)
from api.db import get_db_path
from api.server import app


def test_get_db_path_default(monkeypatch):
    monkeypatch.delenv("DB_PATH", raising=False)
    assert get_db_path() == "./agent_tasks.db"


def test_get_db_path_custom(monkeypatch):
    monkeypatch.setenv("DB_PATH", "/tmp/custom.db")
    assert get_db_path() == "/tmp/custom.db"


def _make_run(run_id: str) -> Run:
    return Run(
        run_id=run_id,
        task="do a thing",
        expect_schema=None,
        budget=RunBudget(steps=20, usd=1.0, seconds=300),
        llm=RunLLM(
            base_url="http://localhost:8090",
            model="test-model",
            temperature=0.0,
            seed=None,
        ),
        agent_version="test",
        started_at="2024-01-01T00:00:00Z",
        ended_at=None,
        status=None,
        final=None,
        totals=None,
    )


_MOCK_RESULT = RunResult(
    status="succeeded",
    result={"ok": True},
    evidence={"url": "http://x", "text_snippet": "x"},
    verifier={"ok": True, "reasons": []},
)


@pytest.fixture
def temp_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("DB_PATH", db_path)
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:9999")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    return db_path


@pytest.fixture
def client(temp_db):
    return TestClient(app)


def test_post_tasks_returns_id(client, temp_db, monkeypatch):
    monkeypatch.setattr("api.server.loop", lambda *a, **kw: _MOCK_RESULT)
    resp = client.post("/tasks", json={"task": "do a thing"})
    assert resp.status_code == 200
    body = resp.json()
    assert "id" in body
    assert isinstance(body["id"], str)
    assert len(body["id"]) > 0


def test_post_tasks_missing_task_returns_422(client):
    resp = client.post("/tasks", json={})
    assert resp.status_code == 422


def test_post_tasks_empty_task_returns_422(client):
    resp = client.post("/tasks", json={"task": ""})
    assert resp.status_code == 422


def test_post_tasks_creates_run_record(client, temp_db, monkeypatch):
    monkeypatch.setattr("api.server.loop", lambda *a, **kw: _MOCK_RESULT)
    resp = client.post("/tasks", json={"task": "do a thing"})
    assert resp.status_code == 200
    run_id = resp.json()["id"]
    conn = sqlite3.connect(temp_db)
    rows = conn.execute("SELECT run_id FROM traces_runs").fetchall()
    conn.close()
    assert len(rows) == 1
    assert rows[0][0] == run_id


def test_get_task_running(client, temp_db):
    run_id = "run-running-001"
    writer = TraceWriter(temp_db)
    writer.open_run(_make_run(run_id))
    writer.close()
    resp = client.get(f"/tasks/{run_id}")
    assert resp.status_code == 200
    assert resp.json() == {"status": "running"}


def test_get_task_completed(client, temp_db):
    run_id = "run-completed-001"
    writer = TraceWriter(temp_db)
    writer.open_run(_make_run(run_id))
    writer.close_run(
        run_id,
        status="succeeded",
        ended_at="2024-01-01T00:01:00Z",
        final={
            "result": {"ok": True},
            "evidence": {"url": "http://x", "text_snippet": "x"},
            "failure": None,
        },
        totals={
            "steps": 1,
            "llm_calls": 1,
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "usd": 0.0,
            "browser_ms": 100,
        },
    )
    writer.close()
    resp = client.get(f"/tasks/{run_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "succeeded"


def test_get_task_not_found(client):
    resp = client.get("/tasks/nonexistent-id")
    assert resp.status_code == 404


def test_get_trace_returns_ndjson(client, temp_db):
    run_id = "run-trace-001"
    writer = TraceWriter(temp_db)
    writer.open_run(_make_run(run_id))
    writer.append_event(
        ObservationEvent(
            run_id=run_id,
            seq=1,
            ts="2024-01-01T00:00:01Z",
            step_id=None,
            url="http://example.com",
            title="Example",
            ax_tree_digest="",
            ax_fingerprint="",
            screenshot_ref="",
            viewport={"width": 1280, "height": 720},
        )
    )
    writer.append_event(
        DoneEvent(
            run_id=run_id,
            seq=2,
            ts="2024-01-01T00:00:02Z",
            step_id=None,
            result={"ok": True},
            evidence={"url": "http://x", "text_snippet": "x"},
            verifier={"ok": True, "reasons": []},
        )
    )
    writer.close()
    resp = client.get(f"/tasks/{run_id}/trace")
    assert resp.status_code == 200
    assert "application/x-ndjson" in resp.headers["content-type"]
    lines = [line for line in resp.text.split("\n") if line.strip()]
    assert len(lines) == 2


def test_get_trace_events_ordered_by_seq(client, temp_db):
    run_id = "run-trace-ordered-001"
    writer = TraceWriter(temp_db)
    writer.open_run(_make_run(run_id))
    writer.append_event(
        ObservationEvent(
            run_id=run_id,
            seq=1,
            ts="2024-01-01T00:00:01Z",
            step_id=None,
            url="http://example.com",
            title="Example",
            ax_tree_digest="",
            ax_fingerprint="",
            screenshot_ref="",
            viewport={"width": 1280, "height": 720},
        )
    )
    writer.append_event(
        DoneEvent(
            run_id=run_id,
            seq=2,
            ts="2024-01-01T00:00:02Z",
            step_id=None,
            result={"ok": True},
            evidence={"url": "http://x", "text_snippet": "x"},
            verifier={"ok": True, "reasons": []},
        )
    )
    writer.close()
    resp = client.get(f"/tasks/{run_id}/trace")
    assert resp.status_code == 200
    lines = [line for line in resp.text.split("\n") if line.strip()]
    assert json.loads(lines[0])["seq"] == 1
    assert json.loads(lines[1])["seq"] == 2


def test_get_trace_not_found(client):
    resp = client.get("/tasks/nonexistent-id/trace")
    assert resp.status_code == 404


def test_get_trace_empty_for_running_run(client, temp_db):
    run_id = "run-trace-empty-001"
    writer = TraceWriter(temp_db)
    writer.open_run(_make_run(run_id))
    writer.close()
    resp = client.get(f"/tasks/{run_id}/trace")
    assert resp.status_code == 200
    lines = [line for line in resp.text.split("\n") if line.strip()]
    assert len(lines) == 0


def test_root_returns_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert "<form" in resp.text
    assert "task" in resp.text


def test_run_agent_closes_writer_on_loop_exception(temp_db, monkeypatch):
    closed_calls: list[bool] = []

    original_close = TraceWriter.close

    def tracking_close(self: TraceWriter) -> None:
        closed_calls.append(True)
        original_close(self)

    def _raise(*_a, **_kw):
        raise RuntimeError("boom")

    monkeypatch.setattr(TraceWriter, "close", tracking_close)
    monkeypatch.setattr("api.server.loop", _raise)

    from api.server import TaskRequest, _run_agent

    run_id = "run-exc-001"
    writer = TraceWriter(temp_db)
    writer.open_run(_make_run(run_id))
    writer.close()

    _run_agent(run_id, TaskRequest(task="do a thing"))
    assert len(closed_calls) >= 1
