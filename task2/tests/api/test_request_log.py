"""Structured per-request access logs as JSON.

Every API request emits exactly one log line containing `request_id`,
`route`, `status`, `latency_ms`, and (when present in the path)
`run_id`. The `request_id` is also returned in the response header so
clients can correlate logs to specific calls. `token_id` is a
placeholder until the auth middleware lands; we already emit the field
so the schema is stable.
"""

from __future__ import annotations

import json
import logging
import re

import pytest
from fastapi.testclient import TestClient

from api.server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:9999")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    return TestClient(app)


_UUID_RE = re.compile(r"^[0-9a-f-]{8,}$")


def _access_log_records(records: list[logging.LogRecord]) -> list[dict]:
    payloads = []
    for r in records:
        if r.name != "api.access":
            continue
        try:
            payloads.append(json.loads(r.getMessage()))
        except json.JSONDecodeError:
            continue
    return payloads


def test_request_log_is_single_json_line_per_request(client, caplog):
    caplog.set_level(logging.INFO, logger="api.access")
    resp = client.get("/healthz")
    assert resp.status_code == 200

    logs = _access_log_records(caplog.records)
    assert len(logs) == 1
    log = logs[0]
    assert log["route"] == "/healthz"
    assert log["status"] == 200
    assert log["method"] == "GET"
    assert isinstance(log["latency_ms"], (int, float))
    assert log["latency_ms"] >= 0
    assert _UUID_RE.match(log["request_id"])
    # Stable schema for forward-compat with auth (not yet wired)
    assert "token_id" in log
    assert "run_id" in log


def test_request_log_includes_run_id_when_in_path(client, caplog):
    """When the path contains a `run_id`, the log line carries it so
    operators can correlate access logs with trace records."""
    caplog.set_level(logging.INFO, logger="api.access")
    resp = client.get("/tasks/some-run-id")
    # 404 for unknown run is expected; log shape is what we're asserting.
    assert resp.status_code == 404

    logs = _access_log_records(caplog.records)
    assert len(logs) == 1
    assert logs[0]["run_id"] == "some-run-id"
    assert logs[0]["status"] == 404


def test_request_id_returned_in_response_header(client):
    """The same request_id used in the log appears in the
    `x-request-id` response header so clients can quote it in support
    tickets without grepping logs."""
    resp = client.get("/healthz")
    rid = resp.headers.get("x-request-id")
    assert rid is not None
    assert _UUID_RE.match(rid)


def test_request_id_uses_client_supplied_header_when_present(client):
    """If the caller supplies `x-request-id`, we honor it (idempotency
    + cross-system tracing). Otherwise we mint a UUID. Plain string
    pass-through, no re-encoding."""
    incoming = "trace-from-upstream-42"
    resp = client.get("/healthz", headers={"x-request-id": incoming})
    assert resp.headers.get("x-request-id") == incoming
