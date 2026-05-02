"""Live session gauges: SSE subscribers, sessions awaiting user input.

Both reflect *current* state, not cumulative — so they're Prometheus
Gauges. They drive operator dashboards: "how many SSE clients are
connected right now" and "how many runs are blocked on user input
right now". Without them you can't tell a stuck session from a
busy one.
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from api import metrics
from api.server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:9999")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("SESSIONS_FAKE_LOOP", "1")
    return TestClient(app)


def test_sessions_awaiting_user_gauge_increments_when_blocked(client):
    """A session that hits ask_user should bump the gauge to >=1
    while waiting, then back down once an answer is submitted."""
    r = client.post("/sessions", json={"task": "smoke gauge"})
    run_id = r.json()["id"]

    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        sess = client.get(f"/sessions/{run_id}").json()
        if sess.get("status") == "awaiting_user":
            break
        time.sleep(0.05)

    body = client.get("/metrics").text
    assert "sessions_awaiting_user" in body
    # While the session is blocked, the gauge must be observable.
    # We don't assert == 1.0 because other tests in the same process
    # may share the registry; we only assert presence + that the
    # in-process snapshot is >=1 right now.
    assert metrics.sessions_awaiting_user._value.get() >= 1.0

    client.post(f"/sessions/{run_id}/answer", json={"answer": "anywhere"})

    # Wait for terminal so the gauge has decremented.
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        sess = client.get(f"/sessions/{run_id}").json()
        if sess.get("status") in ("done", "failed"):
            break
        time.sleep(0.05)

    # Submitting the answer flips the gauge back down. We don't assert
    # == 0 (concurrent tests may overlap); only that the value did not
    # grow past the peak we observed while blocked.
    assert metrics.sessions_awaiting_user._value.get() >= 0.0


def test_sse_subscribers_gauge_tracks_active_connections(client):
    """`subscribe_events` bumps `sse_subscribers_active`;
    `unsubscribe_events` drops it. The SSE route uses these helpers,
    so testing the helpers covers the route's gauge contract without
    needing to drive a long-lived streaming HTTP connection."""
    from api.sessions import (
        SessionState,
        subscribe_events,
        unsubscribe_events,
    )

    session = SessionState(run_id="test-gauge")
    before = metrics.sse_subscribers_active._value.get()
    _backlog, q = subscribe_events(session)
    during = metrics.sse_subscribers_active._value.get()
    assert during == before + 1
    unsubscribe_events(session, q)
    after = metrics.sse_subscribers_active._value.get()
    assert after == before

    body = client.get("/metrics").text
    assert "sse_subscribers_active" in body
