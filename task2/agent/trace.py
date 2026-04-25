"""Trace schema and append-only SQLite writer for the agent loop.

Models: Run, EventBase + 8 event variants, AnyEvent (discriminated union).
Writer: TraceWriter (append-only, strictly-increasing seq, redaction before write).
"""

from __future__ import annotations

import json
import re
import sqlite3
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter


class EventBase(BaseModel):
    run_id: str
    seq: int
    ts: str
    step_id: str | None
    kind: str


class ObservationEvent(EventBase):
    kind: Literal["observation"] = "observation"
    url: str
    title: str
    ax_tree_digest: str
    ax_fingerprint: str
    screenshot_ref: str
    viewport: dict[str, Any]


class PlanEvent(EventBase):
    kind: Literal["plan"] = "plan"
    reason: Literal["initial", "replan"]
    steps: list[str]
    llm_call_id: str


class DecisionEvent(EventBase):
    kind: Literal["decision"] = "decision"
    intent: str
    tool: Literal[
        "goto", "click", "type", "select", "read", "wait_for", "back", "screenshot", "done", "fail"
    ]
    args: dict[str, Any]
    rationale: str
    llm_call_id: str


class LocateEvent(EventBase):
    kind: Literal["locate"] = "locate"
    intent: str
    tier: Literal["cache", "L1_ax", "L2_dom", "L3_rerank", "L4_vision"]
    outcome: Literal["hit", "miss", "ambiguous", "error"]
    candidates: list[dict[str, Any]]
    chosen: dict[str, Any] | None
    cache_action: Literal["read", "write", "invalidate"] | None
    ms: int


class ActEvent(EventBase):
    kind: Literal["act"] = "act"
    tool: str
    args: dict[str, Any]
    outcome: Literal["ok", "no_effect", "nav", "timeout", "error"]
    diff: dict[str, Any]
    ms: int


class SupervisorEvent(EventBase):
    kind: Literal["supervisor"] = "supervisor"
    trigger_event_seq: int
    classified_as: Literal[
        "LocatorMiss", "Ambiguous", "NoEffect", "FormError", "NavDrift", "Blocked", "Timeout"
    ]
    policy: Literal["next_tier", "rerank", "sweep_overlay", "replan", "halt"]
    attempt: int


class LLMCallEvent(EventBase):
    kind: Literal["llm_call"] = "llm_call"
    llm_call_id: str
    purpose: Literal[
        "plan", "decide", "locate_rerank", "locate_vision", "classify_failure", "verify_evidence"
    ]
    model: str
    base_url: str
    prompt: dict[str, Any]
    response: dict[str, Any]
    tokens: dict[str, Any]
    usd: float
    ms: int


class DoneEvent(EventBase):
    kind: Literal["done"] = "done"
    result: dict[str, Any]
    evidence: dict[str, Any]
    verifier: dict[str, Any]


AnyEvent = Annotated[
    ObservationEvent
    | PlanEvent
    | DecisionEvent
    | LocateEvent
    | ActEvent
    | SupervisorEvent
    | LLMCallEvent
    | DoneEvent,
    Field(discriminator="kind"),
]

_any_event_adapter: TypeAdapter[AnyEvent] = TypeAdapter(AnyEvent)


class Run(BaseModel):
    run_id: str
    task: str
    expect_schema: dict[str, Any] | None
    budget: dict[str, Any]
    llm: dict[str, Any]
    agent_version: str
    started_at: str
    ended_at: str | None
    status: Literal["succeeded", "unverified", "failed", "blocked", "timeout"] | None
    final: dict[str, Any] | None
    totals: dict[str, Any] | None


class SeqError(ValueError):
    def __init__(self, *, expected_min: int, got: int) -> None:
        self.expected_min = expected_min
        self.got = got
        super().__init__(f"Expected seq >= {expected_min}, got {got}")


_SECRET_HEADER_PATTERN = re.compile(r"(?i)(set-cookie|cookie|authorization):\s*[^\r\n]+")


def redact(event: AnyEvent) -> AnyEvent:
    """Return a new event with secret fields replaced by '[REDACTED]'."""
    if isinstance(event, LLMCallEvent):
        old_messages: list[dict[str, Any]] = event.prompt.get("messages", [])
        new_messages = []
        for msg in old_messages:
            content = msg.get("content")
            if isinstance(content, str) and _SECRET_HEADER_PATTERN.search(content):
                new_content = _SECRET_HEADER_PATTERN.sub("[REDACTED]", content)
                new_messages.append({**msg, "content": new_content})
            else:
                new_messages.append(msg)
        new_prompt = {**event.prompt, "messages": new_messages}
        return event.model_copy(update={"prompt": new_prompt}, deep=True)

    if isinstance(event, DecisionEvent) and event.tool == "type" and "text" in event.args:
        new_args = {**event.args, "text": "[REDACTED]"}
        return event.model_copy(update={"args": new_args}, deep=True)

    return event


_CREATE_RUNS_SQL = """\
CREATE TABLE IF NOT EXISTS traces_runs (
    run_id TEXT PRIMARY KEY NOT NULL,
    payload TEXT NOT NULL,
    status TEXT,
    ended_at TEXT,
    final_json TEXT,
    totals_json TEXT
)"""

_CREATE_EVENTS_SQL = """\
CREATE TABLE IF NOT EXISTS traces_events (
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    payload TEXT NOT NULL,
    UNIQUE(run_id, seq)
)"""

_INSERT_RUN_SQL = "INSERT INTO traces_runs (run_id, payload) VALUES (?, ?)"
_MAX_SEQ_SQL = "SELECT MAX(seq) FROM traces_events WHERE run_id = ?"
_INSERT_EVENT_SQL = "INSERT INTO traces_events (run_id, seq, payload) VALUES (?, ?, ?)"
_UPDATE_RUN_SQL = (
    "UPDATE traces_runs "
    "SET status = ?, ended_at = ?, final_json = ?, totals_json = ? "
    "WHERE run_id = ?"
)


class TraceWriter:
    """Append-only SQLite writer for Run headers and Event streams."""

    def __init__(self, path: str = ":memory:") -> None:
        self._conn: sqlite3.Connection | None = sqlite3.connect(path)
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        assert self._conn is not None
        self._conn.execute(_CREATE_RUNS_SQL)
        self._conn.execute(_CREATE_EVENTS_SQL)
        self._conn.commit()

    def _require_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise sqlite3.ProgrammingError("Cannot operate on a closed TraceWriter.")
        return self._conn

    def open_run(self, run: Run) -> None:
        conn = self._require_conn()
        conn.execute(_INSERT_RUN_SQL, (run.run_id, run.model_dump_json()))
        conn.commit()

    def append_event(self, event: AnyEvent) -> None:  # type: ignore[override]
        conn = self._require_conn()
        row = conn.execute(_MAX_SEQ_SQL, (event.run_id,)).fetchone()
        max_seq: int | None = row[0] if row else None
        if max_seq is not None and event.seq <= max_seq:
            raise SeqError(expected_min=max_seq + 1, got=event.seq)
        clean_event = redact(event)
        conn.execute(
            _INSERT_EVENT_SQL,
            (clean_event.run_id, clean_event.seq, clean_event.model_dump_json()),
        )
        conn.commit()

    def close_run(
        self,
        run_id: str,
        *,
        status: str,
        ended_at: str,
        final: dict[str, Any],
        totals: dict[str, Any],
    ) -> None:
        conn = self._require_conn()
        conn.execute(
            _UPDATE_RUN_SQL,
            (status, ended_at, json.dumps(final), json.dumps(totals), run_id),
        )
        conn.commit()

    def close(self) -> None:
        if self._conn is None:
            return
        self._conn.close()
        self._conn = None

    def __enter__(self) -> TraceWriter:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()
