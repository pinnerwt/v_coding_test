from __future__ import annotations

import json
import logging
import os
import sqlite3
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, field_validator
from ulid import ULID

from agent.browser import Browser
from agent.llm import _DEFAULT_LLM_MODEL, LLMClient
from agent.loop import RunResult, loop
from agent.trace import Run, RunBudget, RunLLM, TraceWriter
from api.db import get_db_path
from api.sessions import (
    get_session,
    start_session,
    submit_answer,
    subscribe_events,
    unsubscribe_events,
)

logger = logging.getLogger(__name__)

_AGENT_VERSION = "0.1.0"

_ZERO_TOTALS: dict[str, Any] = {
    "steps": 0,
    "llm_calls": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "usd": 0.0,
    "browser_ms": 0,
}

app = FastAPI()


def _probe_db() -> bool:
    """Open a short connection to the trace DB and run a no-op query.

    Cheap: SQLite open + `SELECT 1` is sub-millisecond on a healthy disk.
    Raises on any sqlite3 error; the caller treats that as `db: False`.
    """
    with sqlite3.connect(get_db_path(), timeout=1.0) as conn:
        conn.execute("SELECT 1").fetchone()
    return True


def _probe_llm() -> bool:
    """HEAD the configured LLM_BASE_URL with a tight timeout.

    Any 2xx/3xx/4xx is treated as "endpoint is up" — the LLM's own auth
    or routing might 404 a HEAD, but the network path is healthy and the
    upstream is responding. Connection refused / DNS error / timeout
    raises and the caller treats that as `llm: False`. Kept under 1 s so
    a stuck endpoint doesn't dominate the probe budget.
    """
    base_url = os.environ.get("LLM_BASE_URL", "http://localhost:8090")
    with httpx.Client(timeout=1.0) as client:
        client.head(base_url)
    return True


@app.get("/healthz")
def healthz() -> dict[str, Any]:
    """Bare liveness probe — process is up and responsive.

    Intentionally dependency-free: a flaky DB or LLM endpoint must not
    trigger a process-restart loop. Use `/readyz` for traffic admission.
    """
    return {"status": "ok"}


@app.get("/readyz")
def readyz() -> JSONResponse:
    """Readiness probe — DB and LLM endpoint reachable.

    Returns 200 with each dependency's status when all green; 503 with
    the same payload when any check fails. A deploy controller reads
    this to drain old pods before flipping traffic.
    """
    checks: dict[str, bool] = {}
    try:
        checks["db"] = _probe_db()
    except Exception:
        checks["db"] = False
    try:
        checks["llm"] = _probe_llm()
    except Exception:
        checks["llm"] = False
    all_ok = all(checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ready" if all_ok else "not_ready", "checks": checks},
    )


class TaskRequest(BaseModel):
    task: str
    expect_schema: dict | None = None
    budget: dict | None = None
    locale: str | None = None

    @field_validator("task")
    @classmethod
    def task_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("task must not be empty")
        return v


def _build_run(run_id: str, task_req: TaskRequest) -> Run:
    base_url = os.environ.get("LLM_BASE_URL", "http://localhost:8090")
    model = os.environ.get("LLM_MODEL", _DEFAULT_LLM_MODEL)
    return Run(
        run_id=run_id,
        task=task_req.task,
        expect_schema=task_req.expect_schema,
        budget=RunBudget(steps=20, usd=1.0, seconds=300),
        llm=RunLLM(base_url=base_url, model=model, temperature=0.0, seed=None),
        agent_version=_AGENT_VERSION,
        started_at=datetime.now(UTC).isoformat(),
        ended_at=None,
        status=None,
        final=None,
        totals=None,
    )


def _run_agent(run_id: str, task_req: TaskRequest) -> None:
    writer = TraceWriter(get_db_path())
    try:
        with (
            LLMClient(model=os.environ.get("LLM_MODEL", _DEFAULT_LLM_MODEL)) as llm_client,
            Browser() as browser,
        ):
            result: RunResult = loop(
                task_req.task,
                browser,
                llm_client,
                trace_writer=writer,
                run_id=run_id,
            )
        ended_at = datetime.now(UTC).isoformat()
        writer.close_run(
            run_id,
            status=result.status,
            ended_at=ended_at,
            final={
                "result": result.result,
                "evidence": result.evidence,
                "failure": None if result.status != "failed" else {"reason": "agent failed"},
            },
            totals=_ZERO_TOTALS,
        )
    except Exception:
        logger.exception("agent run failed", extra={"run_id": run_id})
        ended_at = datetime.now(UTC).isoformat()
        try:
            writer.close_run(
                run_id,
                status="failed",
                ended_at=ended_at,
                final={"result": None, "evidence": None, "failure": {"reason": "internal error"}},
                totals=_ZERO_TOTALS,
            )
        except Exception:
            pass
    finally:
        writer.close()


@app.post("/tasks")
def create_task(task_req: TaskRequest, background_tasks: BackgroundTasks) -> dict[str, Any]:
    run_id = str(ULID())
    run = _build_run(run_id, task_req)
    writer = TraceWriter(get_db_path())
    try:
        writer.open_run(run)
    finally:
        writer.close()
    background_tasks.add_task(_run_agent, run_id, task_req)
    return {"id": run_id}


@app.get("/tasks/{run_id}")
def get_task(run_id: str) -> dict[str, Any]:
    try:
        with sqlite3.connect(get_db_path()) as conn:
            row = conn.execute(
                "SELECT status, payload FROM traces_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
    except sqlite3.OperationalError:
        raise HTTPException(status_code=404, detail="not found") from None
    if row is None:
        raise HTTPException(status_code=404, detail="not found")
    status, payload = row
    if status is None:
        return {"status": "running"}
    return json.loads(payload)


def _trace_events_generator(run_id: str, db_path: str) -> Generator[str, None, None]:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute(
            "SELECT payload FROM traces_events WHERE run_id = ? ORDER BY seq ASC", (run_id,)
        )
        for (payload,) in cursor:
            yield payload + "\n"
    finally:
        conn.close()


@app.get("/tasks/{run_id}/trace")
def get_trace(run_id: str) -> StreamingResponse:
    db_path = get_db_path()
    try:
        with sqlite3.connect(db_path) as conn:
            exists = conn.execute(
                "SELECT 1 FROM traces_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
    except sqlite3.OperationalError:
        raise HTTPException(status_code=404, detail="not found") from None
    if exists is None:
        raise HTTPException(status_code=404, detail="not found")
    return StreamingResponse(
        _trace_events_generator(run_id, db_path),
        media_type="application/x-ndjson",
    )


_STATIC_DIR = Path(__file__).parent / "static"
_CHAT_HTML = (_STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/")
def root() -> HTMLResponse:
    return HTMLResponse(_CHAT_HTML)


@app.get("/chat")
def chat() -> HTMLResponse:
    return HTMLResponse(_CHAT_HTML)


class AnswerRequest(BaseModel):
    answer: str

    @field_validator("answer")
    @classmethod
    def answer_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("answer must not be empty")
        return v


@app.post("/sessions")
def create_session(task_req: TaskRequest) -> dict[str, Any]:
    run_id = start_session(
        task_req.task,
        expect_schema=task_req.expect_schema,
        locale=task_req.locale,
    )
    return {"id": run_id}


@app.get("/sessions/{run_id}")
def get_session_status(run_id: str) -> dict[str, Any]:
    session = get_session(run_id)
    if session is None:
        raise HTTPException(status_code=404, detail="not found")
    result_payload = session.result.result if session.result is not None else None
    return {
        "run_id": session.run_id,
        "status": session.status,
        "pending_question": session.pending_question,
        "result": result_payload,
    }


@app.post("/sessions/{run_id}/answer")
def post_session_answer(run_id: str, body: AnswerRequest) -> dict[str, Any]:
    session = get_session(run_id)
    if session is None:
        raise HTTPException(status_code=404, detail="not found")
    try:
        submit_answer(session, body.answer)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return {"ok": True}


@app.get("/sessions/{run_id}/events")
def get_session_events(run_id: str) -> StreamingResponse:
    session = get_session(run_id)
    if session is None:
        raise HTTPException(status_code=404, detail="not found")

    backlog, q = subscribe_events(session)

    def gen() -> Generator[str, None, None]:
        try:
            terminal_seen = False
            for ev in backlog:
                yield f"data: {json.dumps(ev)}\n\n"
                if ev.get("type") == "terminal":
                    terminal_seen = True
            if terminal_seen:
                return
            while True:
                try:
                    ev = q.get(timeout=15)
                except Exception:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(ev)}\n\n"
                if ev.get("type") == "terminal":
                    return
        finally:
            unsubscribe_events(session, q)

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)
