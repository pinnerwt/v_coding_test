from __future__ import annotations

import json
import os
import sqlite3
from collections.abc import Generator
from datetime import UTC, datetime
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel, field_validator
from ulid import ULID

from agent.browser import Browser
from agent.llm import LLMClient
from agent.loop import RunResult, loop
from agent.trace import Run, RunBudget, RunLLM, TraceWriter
from api.db import get_db_path

_AGENT_VERSION = "0.1.0"

app = FastAPI()


class TaskRequest(BaseModel):
    task: str
    expect_schema: dict | None = None
    budget: dict | None = None

    @field_validator("task")
    @classmethod
    def task_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("task must not be empty")
        return v


def _build_run(run_id: str, task_req: TaskRequest) -> Run:
    base_url = os.environ.get("LLM_BASE_URL", "http://localhost:8090")
    model = os.environ.get("LLM_MODEL", "")
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
        llm_client = LLMClient()
        with Browser() as browser:
            result: RunResult = loop(task_req.task, browser, llm_client)
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
            totals={
                "steps": 0,
                "llm_calls": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "usd": 0.0,
                "browser_ms": 0,
            },
        )
    except Exception:
        ended_at = datetime.now(UTC).isoformat()
        try:
            writer.close_run(
                run_id,
                status="failed",
                ended_at=ended_at,
                final={"result": None, "evidence": None, "failure": {"reason": "internal error"}},
                totals={
                    "steps": 0,
                    "llm_calls": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "usd": 0.0,
                    "browser_ms": 0,
                },
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
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            "SELECT payload FROM traces_events WHERE run_id = ? ORDER BY seq ASC", (run_id,)
        ).fetchall()
    for (payload,) in rows:
        yield payload + "\n"


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


_HTML = """<!DOCTYPE html>
<html>
<head><title>Agent Task Runner</title></head>
<body>
<h1>Run a Task</h1>
<form id="task-form">
  <label>task: <input id="task-input" name="task" type="text" size="60" /></label>
  <button type="submit">Run</button>
</form>
<pre id="result"></pre>
<script>
document.getElementById('task-form').addEventListener('submit', async function(e) {
  e.preventDefault();
  const task = document.getElementById('task-input').value;
  const pre = document.getElementById('result');
  pre.textContent = 'Submitting...';
  const resp = await fetch('/tasks', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({task})
  });
  const data = await resp.json();
  const id = data.id;
  pre.textContent = 'Running (id=' + id + ')...';
  const poll = setInterval(async function() {
    const r = await fetch('/tasks/' + id);
    const body = await r.json();
    if (body.status !== 'running') {
      clearInterval(poll);
      pre.textContent = JSON.stringify(body, null, 2);
    }
  }, 2000);
});
</script>
</body>
</html>"""


@app.get("/")
def root() -> HTMLResponse:
    return HTMLResponse(_HTML)
