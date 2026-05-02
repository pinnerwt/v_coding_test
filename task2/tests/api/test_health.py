"""Health and readiness probes (`/healthz`, `/readyz`).

`/healthz` is a bare process-up signal: if the FastAPI app is responsive
at all, it returns 200. No dependency checks — this is what a load
balancer or process manager polls to decide whether to restart the pod.

`/readyz` reports whether the service is ready to take traffic: DB
reachable, LLM endpoint reachable. Browser-launch sanity is intentionally
*not* in the request path — Playwright start-up is ~1 s and would dominate
the probe budget. Failure of any checked dependency returns 503 so a
deploy controller can drain before flipping traffic.
"""

from __future__ import annotations

import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from api.server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:9999")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    return TestClient(app)


def test_healthz_returns_200(client):
    """`/healthz` is a bare liveness probe; it returns 200 with no
    dependency checks. Kept dependency-free so a temporarily-broken DB
    or LLM doesn't trigger a restart loop."""
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"


def test_readyz_returns_200_when_dependencies_healthy(client, monkeypatch):
    """`/readyz` returns 200 when DB and LLM probes both succeed."""
    monkeypatch.setattr("api.server._probe_llm", lambda: True)
    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ready"
    assert body["checks"]["db"] is True
    assert body["checks"]["llm"] is True


def test_readyz_returns_503_when_db_unreachable(client, monkeypatch):
    """`/readyz` returns 503 when the DB probe raises. Caller-visible
    body still names which check failed so the operator can act."""
    monkeypatch.setattr("api.server._probe_llm", lambda: True)

    def _broken_db_probe() -> bool:
        raise sqlite3.OperationalError("disk full")

    monkeypatch.setattr("api.server._probe_db", _broken_db_probe)
    resp = client.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["db"] is False
    assert body["checks"]["llm"] is True


def test_readyz_returns_503_when_llm_unreachable(client, monkeypatch):
    """`/readyz` returns 503 when the LLM probe times out / refuses.
    Drain-on-deploy depends on this signal flipping promptly."""

    def _timeout_llm_probe() -> bool:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr("api.server._probe_llm", _timeout_llm_probe)
    resp = client.get("/readyz")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["db"] is True
    assert body["checks"]["llm"] is False
