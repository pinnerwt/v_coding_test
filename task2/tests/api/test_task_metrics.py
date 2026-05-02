"""Task-level Prometheus metrics: completion counter, latency histogram,
failure-class counter.

Wired through the terminal-emit path so both the `/tasks` and
`/sessions` flows feed the same registry. Tests exercise the
session-worker path with `SESSIONS_FAKE_LOOP=1` (no Browser/LLM).
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from api.server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:9999")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("SESSIONS_FAKE_LOOP", "1")
    return TestClient(app)


def _wait_for_terminal(client: TestClient, run_id: str, timeout: float = 5.0) -> dict:
    """Poll /sessions/{id} until status is done|failed (the fake loop is
    fast). Avoids a long-lived SSE connection in unit tests."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/sessions/{run_id}")
        body = resp.json()
        if body.get("status") in ("done", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"session {run_id} did not terminate within {timeout}s")


def test_tasks_completed_counter_increments_on_terminal(client):
    """A `/sessions` run that terminates should bump
    `tasks_completed_total{status="done"}`."""
    # Drive a session that requires one ask_user reply (the fake loop)
    r = client.post("/sessions", json={"task": "smoke task"})
    run_id = r.json()["id"]
    # Fake loop asks for a destination; reply once so it can finish.
    # Poll briefly because the worker thread runs async.
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        sess = client.get(f"/sessions/{run_id}").json()
        if sess.get("status") == "awaiting_user":
            break
        time.sleep(0.05)
    client.post(f"/sessions/{run_id}/answer", json={"answer": "anywhere"})
    _wait_for_terminal(client, run_id)

    body = client.get("/metrics").text
    assert "tasks_completed_total" in body
    # The fake loop returns succeeded → terminal status="done"
    assert 'tasks_completed_total{status="done"}' in body


def test_task_latency_histogram_observed_on_terminal(client):
    """Terminal emit feeds the latency histogram (one observation)."""
    r = client.post("/sessions", json={"task": "smoke task"})
    run_id = r.json()["id"]
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        sess = client.get(f"/sessions/{run_id}").json()
        if sess.get("status") == "awaiting_user":
            break
        time.sleep(0.05)
    client.post(f"/sessions/{run_id}/answer", json={"answer": "anywhere"})
    _wait_for_terminal(client, run_id)

    body = client.get("/metrics").text
    assert "task_latency_seconds_bucket" in body
    assert "task_latency_seconds_count" in body
    # Observed latency >= 0 and the count for status="done" includes our run
    assert 'task_latency_seconds_count{status="done"}' in body


def test_failure_class_counter_emitted_for_unverified(monkeypatch, tmp_path):
    """When a run terminates as `unverified`, the failure-class counter
    increments under the verifier-derived bucket — `self_reported_incomplete`
    when the agent set complete=false, otherwise `unverified`."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:9999")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    # Stub the loop directly via _invoke_loop to inject a custom RunResult.
    from agent.loop import RunResult
    from api import sessions as sessions_mod

    fake_result = RunResult(
        status="unverified",
        result={"answer": "x"},
        evidence={"url": "http://x", "text_snippet": "x"},
        verifier={"ok": False, "reasons": ["self_reported_incomplete: dates"]},
    )

    def fake_invoke(task, *, run_id, expect_schema, ask_user_callback, on_event, locale):
        return fake_result

    monkeypatch.setattr(sessions_mod, "_invoke_loop", fake_invoke)
    client = TestClient(app)
    r = client.post("/sessions", json={"task": "smoke unverified"})
    run_id = r.json()["id"]
    _wait_for_terminal(client, run_id)

    body = client.get("/metrics").text
    assert "tasks_failure_class_total" in body
    assert 'failure_class="self_reported_incomplete"' in body
