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
from agent.trace import Run, RunBudget, RunLLM
from api.db import get_db_path
from api.streaming_trace import StreamingTraceWriter

logger = logging.getLogger(__name__)

SessionStatus = Literal["running", "awaiting_user", "done", "failed"]

_AGENT_VERSION = "0.1.0"


def _terminal_status_label(loop_status: str) -> str:
    """Map RunResult.status to the terminal-event status surface.

    The UI distinguishes succeeded → 'done', and surfaces 'failed'/'unverified'/
    'timeout' explicitly so users see why a run ended.
    """
    return "done" if loop_status == "succeeded" else loop_status


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
    event_log: list[dict[str, Any]] = field(default_factory=list)
    event_subscribers: list[queue.Queue[dict[str, Any]]] = field(default_factory=list)
    event_lock: threading.Lock = field(default_factory=threading.Lock)


_SESSIONS: dict[str, SessionState] = {}
_SESSIONS_LOCK = threading.Lock()


def get_session(run_id: str) -> SessionState | None:
    with _SESSIONS_LOCK:
        return _SESSIONS.get(run_id)


def _register_session(session: SessionState) -> None:
    with _SESSIONS_LOCK:
        _SESSIONS[session.run_id] = session


def emit_event(session: SessionState, payload: dict[str, Any]) -> None:
    """Append to event log and broadcast to subscribers under one lock."""
    with session.event_lock:
        session.event_log.append(payload)
        subs = list(session.event_subscribers)
    for q in subs:
        q.put(payload)


def subscribe_events(
    session: SessionState,
) -> tuple[list[dict[str, Any]], queue.Queue[dict[str, Any]]]:
    """Atomically snapshot the event log and register a live subscriber."""
    q: queue.Queue[dict[str, Any]] = queue.Queue()
    with session.event_lock:
        backlog = list(session.event_log)
        session.event_subscribers.append(q)
    return backlog, q


def unsubscribe_events(session: SessionState, q: queue.Queue[dict[str, Any]]) -> None:
    with session.event_lock:
        try:
            session.event_subscribers.remove(q)
        except ValueError:
            pass


def _make_ask_user_callback(session: SessionState):
    def ask(question: str) -> str:
        session.pending_question = question
        session.status = "awaiting_user"
        emit_event(session, {"type": "ask_user", "question": question})
        try:
            answer = session.answer_queue.get()
        finally:
            session.pending_question = None
            session.status = "running"
        emit_event(session, {"type": "answer", "answer": answer})
        return answer

    return ask


def _invoke_loop(
    task: str,
    *,
    run_id: str,
    expect_schema: dict | None = None,
    ask_user_callback,
    on_event=None,
    locale: str | None = None,
) -> RunResult:
    """Real loop entrypoint. Tests monkeypatch this seam to avoid Browser/LLM."""
    if os.environ.get("SESSIONS_FAKE_LOOP") == "1":
        answer = ask_user_callback("Which destination?")
        return RunResult(
            status="succeeded",
            result={"task": task, "answer": answer},
            evidence={"url": "fake://smoke", "text_snippet": "fake-loop"},
        )
    base_url = os.environ.get("LLM_BASE_URL", "http://localhost:8090")
    model = os.environ.get("LLM_MODEL", _DEFAULT_LLM_MODEL)
    writer = StreamingTraceWriter(get_db_path(), on_event=on_event)
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
                locale=locale,
                max_steps=run.budget.steps,
                budget_seconds=run.budget.seconds,
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


def _worker(
    session: SessionState,
    task: str,
    expect_schema: dict | None,
    locale: str | None,
) -> None:
    cb = _make_ask_user_callback(session)
    on_event = lambda payload: emit_event(session, {"type": "trace", **payload})  # noqa: E731
    try:
        result = _invoke_loop(
            task,
            run_id=session.run_id,
            expect_schema=expect_schema,
            ask_user_callback=cb,
            on_event=on_event,
            locale=locale,
        )
        session.result = result
        session.status = "done" if result.status == "succeeded" else "failed"
        emit_event(
            session,
            {
                "type": "terminal",
                "status": _terminal_status_label(result.status),
                "reason": result.reason,
                "result": result.result,
                "evidence": result.evidence,
            },
        )
    except Exception as exc:
        logger.exception("session worker failed", extra={"run_id": session.run_id})
        session.error = str(exc)
        session.status = "failed"
        emit_event(session, {"type": "terminal", "status": "failed", "error": str(exc)})


def start_session(
    task: str,
    *,
    expect_schema: dict | None = None,
    locale: str | None = None,
) -> str:
    run_id = str(ULID())
    session = SessionState(run_id=run_id)
    _register_session(session)
    thread = threading.Thread(
        target=_worker,
        args=(session, task, expect_schema, locale),
        name=f"session-{run_id}",
        daemon=True,
    )
    thread.start()
    return run_id


def submit_answer(session: SessionState, answer: str) -> None:
    if session.status != "awaiting_user":
        raise RuntimeError("session is not awaiting user input")
    session.answer_queue.put(answer)
