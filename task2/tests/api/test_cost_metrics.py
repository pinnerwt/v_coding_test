"""Cost attribution: LLM token/USD counters + `/usage` endpoint.

LLM call events emitted by the loop carry token counts and a per-call
USD figure. The session worker's `on_event` callback is the natural
hook: every llm_call event flows through it on its way to the SSE
subscribers, so attaching metric updates there means both the
`/sessions` and `/tasks` paths feed the same series.

`/usage` reads the trace store directly (the source of truth for
historical cost), aggregating across all closed runs. Prometheus
counters are for live dashboards; `/usage` is for token-holder
self-check.
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
    return TestClient(app)


def _wait_for_terminal(client: TestClient, run_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/sessions/{run_id}")
        body = resp.json()
        if body.get("status") in ("done", "failed"):
            return body
        time.sleep(0.05)
    raise AssertionError(f"session {run_id} did not terminate within {timeout}s")


def test_llm_token_and_usd_counters_increment_on_llm_call_event(monkeypatch, tmp_path):
    """An llm_call event flowing through `on_event` should bump
    `llm_tokens_total{kind="prompt"|"completion"}` and
    `llm_usd_total`."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:9999")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    from agent.loop import RunResult
    from api import sessions as sessions_mod

    fake_result = RunResult(
        status="succeeded",
        result={"answer": "x"},
        evidence={"url": "http://x", "text_snippet": "x"},
    )

    def fake_invoke(task, *, run_id, expect_schema, ask_user_callback, on_event, locale):
        # Simulate an llm_call trace event being appended by the loop.
        on_event(
            {
                "kind": "llm_call",
                "run_id": run_id,
                "seq": 1,
                "ts": "2026-05-01T00:00:00Z",
                "step_id": "step-1",
                "llm_call_id": "call-1",
                "purpose": "plan",
                "model": "test-model",
                "base_url": "http://localhost:9999",
                "prompt": {},
                "response": {},
                "tokens": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
                "usd": 0.0025,
                "ms": 42,
            }
        )
        return fake_result

    monkeypatch.setattr(sessions_mod, "_invoke_loop", fake_invoke)
    client = TestClient(app)
    r = client.post("/sessions", json={"task": "smoke cost"})
    run_id = r.json()["id"]
    _wait_for_terminal(client, run_id)

    body = client.get("/metrics").text
    assert "llm_tokens_total" in body
    assert 'llm_tokens_total{kind="prompt"}' in body
    assert 'llm_tokens_total{kind="completion"}' in body
    assert "llm_usd_total" in body


def test_usage_endpoint_reports_global_totals(monkeypatch, tmp_path):
    """`/usage` aggregates closed runs from the trace store and reports
    prompt/completion tokens + total USD spend."""
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("LLM_BASE_URL", "http://localhost:9999")
    monkeypatch.setenv("LLM_MODEL", "test-model")

    from agent.loop import RunResult
    from api import sessions as sessions_mod

    fake_result = RunResult(
        status="succeeded",
        result={"answer": "x"},
        evidence={"url": "http://x", "text_snippet": "x"},
    )

    def fake_invoke(task, *, run_id, expect_schema, ask_user_callback, on_event, locale):
        on_event(
            {
                "kind": "llm_call",
                "run_id": run_id,
                "seq": 1,
                "ts": "2026-05-01T00:00:00Z",
                "step_id": "step-1",
                "llm_call_id": "call-1",
                "purpose": "plan",
                "model": "test-model",
                "base_url": "http://localhost:9999",
                "prompt": {},
                "response": {},
                "tokens": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
                "usd": 0.01,
                "ms": 42,
            }
        )
        return fake_result

    monkeypatch.setattr(sessions_mod, "_invoke_loop", fake_invoke)
    client = TestClient(app)
    r = client.post("/sessions", json={"task": "smoke usage"})
    run_id = r.json()["id"]
    _wait_for_terminal(client, run_id)

    resp = client.get("/usage")
    assert resp.status_code == 200
    body = resp.json()
    # Schema: prompt_tokens, completion_tokens, usd, runs (count of closed runs)
    assert "prompt_tokens" in body
    assert "completion_tokens" in body
    assert "usd" in body
    assert body["prompt_tokens"] >= 100
    assert body["completion_tokens"] >= 50
    assert body["usd"] >= 0.0099  # float tolerance
