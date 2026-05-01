"""Trace-event sampling via OBSERVE_LEVEL.

Trace events carry potentially-large payloads — the full prompt
messages list on `llm_call` (multi-megabyte at long-context models)
and the screenshot reference path on `observation`. In day-to-day
operation we don't need every byte; in incident response we do.

`OBSERVE_LEVEL=debug` keeps everything (replay-quality traces).
`OBSERVE_LEVEL=info` (the default) strips the large fields at
write-time: the metric-relevant scaffolding (tokens, usd, model,
purpose, ms) stays, but the full prompt/response and screenshot ref
get dropped. The setting is read fresh per-write so an operator
can crank it up during an incident without redeploying — flip the
env, restart the worker, get full fidelity for the next run.
"""

from __future__ import annotations

import json
import sqlite3

from agent.trace import (
    LLMCallEvent,
    ObservationEvent,
    Run,
    RunBudget,
    RunLLM,
)
from api import streaming_trace as streaming_trace_mod


def _make_run() -> Run:
    return Run(
        run_id="r-obs",
        task="t",
        expect_schema=None,
        budget=RunBudget(steps=1, usd=1.0, seconds=10),
        llm=RunLLM(base_url="http://x", model="m", temperature=0.0, seed=None),
        agent_version="0.1.0",
        started_at="2026-05-01T00:00:00Z",
        ended_at=None,
        status=None,
        final=None,
        totals=None,
    )


def _make_llm_call() -> LLMCallEvent:
    return LLMCallEvent(
        run_id="r-obs",
        seq=1,
        ts="2026-05-01T00:00:01Z",
        step_id="step-1",
        llm_call_id="call-1",
        purpose="plan",
        model="m",
        base_url="http://x",
        prompt={"messages": [{"role": "user", "content": "x" * 1000}]},
        response={"choices": [{"message": {"content": "y" * 1000}}]},
        tokens={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        usd=0.01,
        ms=42,
    )


def _make_observation() -> ObservationEvent:
    return ObservationEvent(
        run_id="r-obs",
        seq=2,
        ts="2026-05-01T00:00:02Z",
        step_id="step-1",
        url="http://example.com",
        title="t",
        ax_tree_digest="d",
        ax_fingerprint="f",
        screenshot_ref="/var/agent/shots/r-obs/step-1.png",
        viewport={"w": 1280, "h": 720},
    )


def _read_event_payloads(path: str, run_id: str) -> list[dict]:
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT payload FROM traces_events WHERE run_id = ? ORDER BY seq", (run_id,)
        ).fetchall()
    return [json.loads(r[0]) for r in rows]


def test_info_level_strips_llm_prompt_and_response(tmp_path, monkeypatch):
    """At default level=info, the persisted llm_call event drops the
    full prompt + response payloads while preserving the tokens / usd
    / model fields downstream observability cares about."""
    monkeypatch.setenv("OBSERVE_LEVEL", "info")
    db_path = str(tmp_path / "trace.db")
    writer = streaming_trace_mod.StreamingTraceWriter(db_path)
    writer.open_run(_make_run())
    writer.append_event(_make_llm_call())
    writer.close()

    [persisted] = _read_event_payloads(db_path, "r-obs")
    # Tokens/USD/scaffolding survive — these are what cost dashboards read.
    assert persisted["tokens"]["prompt_tokens"] == 100
    assert persisted["usd"] == 0.01
    assert persisted["model"] == "m"
    # Heavy fields are stripped.
    assert persisted["prompt"] == {} or persisted["prompt"].get("messages") in ([], None)
    assert persisted["response"] == {} or persisted["response"].get("choices") in ([], None)


def test_debug_level_retains_full_payload(tmp_path, monkeypatch):
    """At level=debug, the trace writer is replay-quality — full
    prompt and response payloads make it to disk."""
    monkeypatch.setenv("OBSERVE_LEVEL", "debug")
    db_path = str(tmp_path / "trace.db")
    writer = streaming_trace_mod.StreamingTraceWriter(db_path)
    writer.open_run(_make_run())
    writer.append_event(_make_llm_call())
    writer.close()

    [persisted] = _read_event_payloads(db_path, "r-obs")
    assert persisted["prompt"]["messages"][0]["content"] == "x" * 1000
    assert persisted["response"]["choices"][0]["message"]["content"] == "y" * 1000


def test_info_level_strips_screenshot_ref(tmp_path, monkeypatch):
    """At level=info, observation events have screenshot_ref scrubbed
    to empty string (the field is required, so we can't drop it
    entirely without breaking the schema)."""
    monkeypatch.setenv("OBSERVE_LEVEL", "info")
    db_path = str(tmp_path / "trace.db")
    writer = streaming_trace_mod.StreamingTraceWriter(db_path)
    writer.open_run(_make_run())
    writer.append_event(_make_observation())
    writer.close()

    [persisted] = _read_event_payloads(db_path, "r-obs")
    assert persisted["screenshot_ref"] == ""
