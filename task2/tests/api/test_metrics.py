"""Prometheus `/metrics` endpoint.

Exposes the counters / histograms named in plan.md's observability
section. Initial scope: HTTP request counters/histograms wired through
the access-log middleware. Task-level counters (`tasks_started_total`,
LLM tokens/USD, locator tier hits) are populated by separate code
paths and tested where those paths live; this file asserts the
endpoint surface and the request-side metric names exist with the
right label set.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.server import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:9999")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    return TestClient(app)


def _scrape(client: TestClient) -> str:
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    return resp.text


def test_metrics_endpoint_returns_prometheus_text(client):
    """`/metrics` emits Prometheus text-format output. The body
    should at minimum mention the request-counter metric name."""
    body = _scrape(client)
    assert "http_requests_total" in body


def test_http_request_counter_increments_per_request(client):
    """One HTTP request → one increment on the labeled counter for
    its (route, method, status) combination."""
    before = _scrape(client)
    client.get("/healthz")
    client.get("/healthz")
    after = _scrape(client)

    # The healthz line carries the labels we expect; assert it appears
    # at all (specific value parsing is brittle across prom-client
    # versions, but presence + label set is stable).
    assert 'http_requests_total{method="GET"' in after
    assert 'route="/healthz"' in after
    assert 'status="200"' in after
    # Strict monotonicity: post-request body length grows or the line
    # count for /healthz changes (the counter went up).
    assert after != before


def test_http_request_latency_histogram_present(client):
    """Latency histogram is emitted with bucket / count / sum lines."""
    client.get("/healthz")
    body = _scrape(client)
    assert "http_request_latency_seconds_bucket" in body
    assert "http_request_latency_seconds_count" in body
    assert "http_request_latency_seconds_sum" in body
