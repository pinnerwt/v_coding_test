"""Trace schema and append-only SQLite writer for the agent loop.

Models: Run, EventBase + 8 event variants, AnyEvent (discriminated union).
Writer: TraceWriter (append-only, strictly-increasing seq, redaction before write).
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
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
    last_actions: list[dict] = []


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


EscalationPolicy = Literal["next_tier", "rerank", "sweep_overlay", "replan", "halt"]


class SupervisorEvent(EventBase):
    kind: Literal["supervisor"] = "supervisor"
    trigger_event_seq: int
    classified_as: Literal[
        "LocatorMiss",
        "Ambiguous",
        "NoEffect",
        "FormError",
        "NavDrift",
        "Blocked",
        "Timeout",
        "premature_fail",
    ]
    policy: EscalationPolicy
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


class RunBudget(BaseModel):
    steps: int
    usd: float
    seconds: int


class RunLLM(BaseModel):
    base_url: str
    model: str
    temperature: float
    seed: int | None


class RunFinal(BaseModel):
    result: dict[str, Any] | None
    evidence: dict[str, Any] | None
    failure: dict[str, Any] | None


class RunTotals(BaseModel):
    steps: int
    llm_calls: int
    prompt_tokens: int
    completion_tokens: int
    usd: float
    browser_ms: int


class Run(BaseModel):
    run_id: str
    task: str
    expect_schema: dict[str, Any] | None
    budget: RunBudget
    llm: RunLLM
    agent_version: str
    started_at: str
    ended_at: str | None
    status: Literal["succeeded", "unverified", "failed", "blocked", "timeout"] | None
    final: RunFinal | None
    totals: RunTotals | None


class SeqError(ValueError):
    def __init__(self, *, expected_min: int, got: int) -> None:
        self.expected_min = expected_min
        self.got = got
        super().__init__(f"Expected seq >= {expected_min}, got {got}")


_SECRET_HEADER_PATTERN = re.compile(r"(?i)(set-cookie|cookie|authorization):\s*[^\r\n]+")


def redact(event: AnyEvent) -> AnyEvent:
    """Return a new event with secret fields replaced by '[REDACTED]'."""
    if isinstance(event, LLMCallEvent):
        old_messages: list[Any] = event.prompt.get("messages", [])
        new_messages = []
        changed = False
        for msg in old_messages:
            if not isinstance(msg, dict):
                new_messages.append(msg)
                continue
            content = msg.get("content")
            if isinstance(content, str) and _SECRET_HEADER_PATTERN.search(content):
                new_content = _SECRET_HEADER_PATTERN.sub("[REDACTED]", content)
                new_messages.append({**msg, "content": new_content})
                changed = True
            else:
                new_messages.append(msg)
        if not changed:
            return event
        new_prompt = {**event.prompt, "messages": new_messages}
        return event.model_copy(update={"prompt": new_prompt})

    if (
        isinstance(event, DecisionEvent | ActEvent)
        and event.tool == "type"
        and "text" in event.args
    ):
        new_args = {**event.args, "text": "[REDACTED]"}
        return event.model_copy(update={"args": new_args})

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
_RUN_STATE_SQL = (
    "SELECT r.status, "
    "(SELECT MAX(seq) FROM traces_events WHERE run_id = r.run_id) "
    "FROM traces_runs r WHERE r.run_id = ?"
)
_SELECT_RUN_PAYLOAD_SQL = "SELECT payload FROM traces_runs WHERE run_id = ?"
_INSERT_EVENT_SQL = "INSERT INTO traces_events (run_id, seq, payload) VALUES (?, ?, ?)"
_SELECT_EVENTS_SQL = "SELECT payload FROM traces_events WHERE run_id = ? ORDER BY seq"
_UPDATE_RUN_SQL = (
    "UPDATE traces_runs "
    "SET status = ?, ended_at = ?, final_json = ?, totals_json = ?, payload = ? "
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

    @staticmethod
    def _missing_run(run_id: str) -> LookupError:
        return LookupError(f"No open run with run_id={run_id!r}; call open_run first.")

    @staticmethod
    def _closed_run(run_id: str) -> LookupError:
        return LookupError(f"Run {run_id!r} is already closed; cannot append further events.")

    @staticmethod
    def _already_closed(run_id: str) -> ValueError:
        return ValueError(f"Run {run_id!r} is already closed; cannot close it again.")

    def open_run(self, run: Run) -> None:
        if run.status is not None:
            raise ValueError(
                f"open_run requires Run.status to be None; got {run.status!r}. "
                "A run with terminal status cannot be opened."
            )
        conn = self._require_conn()
        conn.execute(_INSERT_RUN_SQL, (run.run_id, run.model_dump_json()))
        conn.commit()

    def append_event(self, event: AnyEvent) -> None:
        conn = self._require_conn()
        state_row = conn.execute(_RUN_STATE_SQL, (event.run_id,)).fetchone()
        if state_row is None:
            raise self._missing_run(event.run_id)
        status, max_seq = state_row
        if status is not None:
            raise self._closed_run(event.run_id)
        if max_seq is not None and event.seq <= max_seq:
            raise SeqError(expected_min=max_seq + 1, got=event.seq)
        clean_event = redact(event)
        conn.execute(
            _INSERT_EVENT_SQL,
            (clean_event.run_id, clean_event.seq, clean_event.model_dump_json()),
        )
        conn.commit()

    def next_seq(self, run_id: str) -> int:
        conn = self._require_conn()
        row = conn.execute(_RUN_STATE_SQL, (run_id,)).fetchone()
        if row is None:
            raise self._missing_run(run_id)
        status, max_seq = row
        if status is not None:
            raise self._closed_run(run_id)
        return (max_seq or 0) + 1

    def iter_events(self, run_id: str) -> Iterator[AnyEvent]:
        conn = self._require_conn()
        return self._iter_events_inner(conn, run_id)

    def _iter_events_inner(self, conn: sqlite3.Connection, run_id: str) -> Iterator[AnyEvent]:
        for row in conn.execute(_SELECT_EVENTS_SQL, (run_id,)):
            yield _any_event_adapter.validate_json(row[0])

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
        payload_row = conn.execute(_SELECT_RUN_PAYLOAD_SQL, (run_id,)).fetchone()
        if payload_row is None:
            raise self._missing_run(run_id)
        existing = Run.model_validate_json(payload_row[0])
        if existing.status is not None:
            raise self._already_closed(run_id)
        run_dict = existing.model_dump()
        run_dict.update(status=status, ended_at=ended_at, final=final, totals=totals)
        updated = Run.model_validate(run_dict)
        assert updated.final is not None and updated.totals is not None
        conn.execute(
            _UPDATE_RUN_SQL,
            (
                updated.status,
                updated.ended_at,
                updated.final.model_dump_json(),
                updated.totals.model_dump_json(),
                updated.model_dump_json(),
                run_id,
            ),
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
