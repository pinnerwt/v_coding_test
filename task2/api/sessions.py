from __future__ import annotations

import logging
import os
import queue
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from ulid import ULID

from agent.browser import Browser
from agent.llm import _DEFAULT_LLM_MODEL, LLMClient
from agent.loop import RunResult, loop
from agent.trace import Run, RunBudget, RunLLM, TraceWriter
from api.db import get_db_path

logger = logging.getLogger(__name__)

SessionStatus = Literal["running", "awaiting_user", "done", "failed"]

_AGENT_VERSION = "0.1.0"

_ZERO_TOTALS: dict[str, Any] = {
    "steps": 0,
    "llm_calls": 0,
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "usd": 0.0,
    "browser_ms": 0,
}


@dataclass
class SessionState:
    run_id: str
    status: SessionStatus = "running"
    pending_question: str | None = None
    answer_queue: queue.Queue[str] = field(default_factory=queue.Queue)
    result: RunResult | None = None
    error: str | None = None


_SESSIONS: dict[str, SessionState] = {}
_SESSIONS_LOCK = threading.Lock()


def get_session(run_id: str) -> SessionState | None:
    with _SESSIONS_LOCK:
        return _SESSIONS.get(run_id)


def _register_session(session: SessionState) -> None:
    with _SESSIONS_LOCK:
        _SESSIONS[session.run_id] = session


def _make_ask_user_callback(session: SessionState):
    def ask(question: str) -> str:
        session.pending_question = question
        session.status = "awaiting_user"
        try:
            answer = session.answer_queue.get()
        finally:
            session.pending_question = None
            session.status = "running"
        return answer

    return ask


def _invoke_loop(
    task: str,
    *,
    run_id: str,
    expect_schema: dict | None = None,
    ask_user_callback,
) -> RunResult:
    """Real loop entrypoint. Tests monkeypatch this seam to avoid Browser/LLM."""
    base_url = os.environ.get("LLM_BASE_URL", "http://localhost:8090")
    model = os.environ.get("LLM_MODEL", _DEFAULT_LLM_MODEL)
    writer = TraceWriter(get_db_path())
    run = Run(
        run_id=run_id,
        task=task,
        expect_schema=expect_schema,
        budget=RunBudget(steps=20, usd=1.0, seconds=300),
        llm=RunLLM(base_url=base_url, model=model, temperature=0.0, seed=None),
        agent_version=_AGENT_VERSION,
        started_at=datetime.now(UTC).isoformat(),
        ended_at=None,
        status=None,
        final=None,
        totals=None,
    )
    try:
        writer.open_run(run)
        with (
            LLMClient(model=model) as llm_client,
            Browser() as browser,
        ):
            result = loop(
                task,
                browser,
                llm_client,
                trace_writer=writer,
                run_id=run_id,
                expect=expect_schema,
                ask_user_callback=ask_user_callback,
            )
        writer.close_run(
            run_id,
            status=result.status,
            ended_at=datetime.now(UTC).isoformat(),
            final={
                "result": result.result,
                "evidence": result.evidence,
                "failure": None if result.status != "failed" else {"reason": "agent failed"},
            },
            totals=_ZERO_TOTALS,
        )
        return result
    finally:
        writer.close()


def _worker(session: SessionState, task: str, expect_schema: dict | None) -> None:
    cb = _make_ask_user_callback(session)
    try:
        result = _invoke_loop(
            task,
            run_id=session.run_id,
            expect_schema=expect_schema,
            ask_user_callback=cb,
        )
        session.result = result
        session.status = "done"
    except Exception as exc:
        logger.exception("session worker failed", extra={"run_id": session.run_id})
        session.error = str(exc)
        session.status = "failed"


def start_session(task: str, *, expect_schema: dict | None = None) -> str:
    run_id = str(ULID())
    session = SessionState(run_id=run_id)
    _register_session(session)
    thread = threading.Thread(
        target=_worker,
        args=(session, task, expect_schema),
        name=f"session-{run_id}",
        daemon=True,
    )
    thread.start()
    return run_id


def submit_answer(session: SessionState, answer: str) -> None:
    if session.status != "awaiting_user":
        raise RuntimeError("session is not awaiting user input")
    session.answer_queue.put(answer)
