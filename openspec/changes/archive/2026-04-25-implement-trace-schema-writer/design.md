## Context

Tickets #1–#11 are complete. The agent loop runs tasks, classifies failures, and enforces evidence. But every run disappears after it finishes — there is no record of what the LLM saw, what it decided, or how locate/supervisor behaved. Ticket #12 introduces `agent/trace.py`: the models and writer that make every run inspectable and replayable.

The plan's "Trace schema (replayable)" section (plan.md lines ~80–202) is the canonical schema. It defines two storage objects — `Run` (one row per task, header) and `Event` (append-only stream, eight variants). Events are stored as JSONL in SQLite; a `Run` header row lives in `traces.runs`.

Existing code style (from `locator_cache.py` and `llm.py`): stdlib first, no runtime deps beyond what's already in the project, `from __future__ import annotations`, frozen dataclasses for pure data. The `LocatorCache` pattern (`:memory:` default, `_ensure_schema()`, context manager) will be reused for `TraceWriter`.

## Goals / Non-Goals

**Goals:**

- Define Pydantic models for `Run` and all eight `Event` variants; every field in plan.md is represented.
- Expose a `TraceWriter` class with an append-only API: `open_run()`, `append_event()`, `close_run()`.
- Enforce strictly increasing `seq` on `append_event()`; raise `SeqError` on out-of-order or duplicate seq.
- Redact secret-typed fields before writing (cookies, auth tokens, user-typed secrets as identified in plan.md "What we deliberately do NOT store").
- Full JSON round-trip for every model: `model.model_dump_json()` → `TypeAdapter.validate_json()` deserializes to an equal object.
- All tests in `task2/tests/agent/test_trace.py` are red-first, then green.
- `uv run ruff check .` is clean.

**Non-Goals:**

- Integration with `loop.py` (separate ticket #13 / replay harness).
- Screenshot storage or `screenshot_ref` resolution — `screenshot_ref` is stored as a plain string path.
- Retention / pruning logic (30-day default, `pinned=true` — separate concern).
- `GET /tasks/{run_id}/trace` HTTP endpoint (ticket #14).
- Schema validation of `Run.expect_schema` or `Run.final.result` against a declared schema.

## Decisions

### Decision 1: Pydantic models, not dataclasses

All models (`Run`, each `Event` variant) use `pydantic.BaseModel` rather than frozen dataclasses. Rationale: JSON serialization (`model_dump_json()`) and deserialization (`model_validate_json()`) are first-class in Pydantic; discriminated unions via `Annotated[Union[...], Field(discriminator="kind")]` handle the eight event variants cleanly without a hand-rolled dispatch. The rest of the codebase uses plain dataclasses for small, non-serialized data; this is the first module that must round-trip through JSON, so the overhead is justified.

**Alternative considered**: dataclasses + `json.dumps` manually. Rejected because nested optional fields (e.g. `LLMCallEvent.prompt.tools`) require hand-written serialization and are error-prone to keep in sync with the schema.

### Decision 2: Event discriminated union via `kind` literal

Each event variant defines `kind: Literal["observation"]` (etc.) as a required field. The public union type is:

```python
AnyEvent = Annotated[
    Union[ObservationEvent, PlanEvent, DecisionEvent, LocateEvent,
          ActEvent, SupervisorEvent, LLMCallEvent, DoneEvent],
    Field(discriminator="kind")
]
```

Deserialization uses `TypeAdapter(AnyEvent).validate_json(line)` — one call, correct subtype returned. Serialization uses `event.model_dump_json()` — no extra dispatch needed.

**Alternative considered**: a single `Event` model with optional fields for each variant. Rejected because it loses type safety and makes the reader guess which fields are populated for a given `kind`.

### Decision 3: ULID IDs via `uuid` for now

Plan.md specifies `run_id: string // ULID`. Rather than adding `python-ulid` as a new dependency, `run_id` defaults to `str(uuid.uuid4())` in tests and the module exposes a `generate_run_id() -> str` helper. The string format is compatible (UUID4 hex is acceptable as a unique ID for our purposes). If the reviewer requires strict ULID format, `python-ulid` can be added as a one-line `uv add` — no model change needed.

**Alternative considered**: `python-ulid` or `ulid-py`. Deferred: adding a dep for cosmetic format when UUID4 already satisfies uniqueness and ordering within a run is tracked by `seq` is unnecessary.

### Decision 4: Shared `EventBase` fields via Pydantic model inheritance

All events share `run_id: str`, `seq: int`, `ts: str` (ISO 8601), `step_id: str | None`. A `EventBase(BaseModel)` captures these; each variant subclasses it and adds its own `kind` literal plus variant-specific fields. This avoids repeating the shared fields eight times and keeps `__init__` signatures tight.

### Decision 5: `TraceWriter` — SQLite-backed, context-manager pattern (mirrors `LocatorCache`)

`TraceWriter(path=":memory:")` opens a SQLite connection and ensures the schema (`traces.runs`, `traces.events`). API:

- `open_run(run: Run) -> None` — INSERT into `traces.runs` (JSON blob for the whole row).
- `append_event(event: AnyEvent) -> None` — validate `seq > last_seq`, then INSERT into `traces.events` as a JSONL line (the raw JSON string). Raise `SeqError(expected, got)` on violation.
- `close_run(run_id: str, *, status: str, ended_at: str, final: dict, totals: dict) -> None` — UPDATE the `traces.runs` row with final fields.
- Context manager: `__enter__`/`__exit__` close the connection.

The `traces.events` table stores the raw JSON string in a `payload TEXT NOT NULL` column, plus `run_id TEXT NOT NULL` and `seq INTEGER NOT NULL` for querying. `(run_id, seq)` is a UNIQUE constraint; duplicate inserts raise `sqlite3.IntegrityError`, which `TraceWriter` re-raises as `SeqError`.

### Decision 6: Redaction — applied at `append_event()` call time, not model construction

The `redact()` helper accepts an `AnyEvent` and returns a new event instance with secret fields replaced by `"[REDACTED]"`. It is called by `TraceWriter.append_event()` before serialization. Fields redacted:

- `LLMCallEvent.prompt.messages`: any message whose `role == "tool"` and whose `content` string contains a pattern matching a cookie header or `Authorization:` header is replaced. More precisely: message `content` strings are scanned for `(?i)(set-cookie|cookie|authorization):\s*\S+`; matching substrings are replaced with `[REDACTED]`.
- `DecisionEvent.args`: if the tool is `"type"` and `args` contains a key `"text"`, the value is replaced with `"[REDACTED]"` (user-typed secrets — passwords, form secrets).
- `LLMCallEvent.prompt.messages` system/user content is NOT redacted (it is the AX tree digest, never raw HTML or cookies per plan.md).

This is conservative. The spec says "cookies / auth tokens / user-typed secrets — redacted before write." The above covers the known vectors at this stage; additional patterns can be added without model changes.

**Alternative considered**: redact at model construction (`model_validator`). Rejected because the model should faithfully represent what the agent produced; stripping happens at persistence time, not at capture time, so in-memory objects are complete for callers who don't persist.

### Decision 7: `seq` assignment vs. validation

The `TraceWriter` only validates that `event.seq > last_seq`; it does NOT auto-assign `seq`. The caller (the loop, in a future ticket) is responsible for assigning monotonically increasing `seq` values. This keeps the writer simple and the caller in control of the ordering. `TraceWriter` raises `SeqError` (a plain `ValueError` subclass) if the invariant is violated.

### Decision 8: No Pydantic dependency added — `pydantic` is already in `pyproject.toml`

Checked: `task2/pyproject.toml` already lists `pydantic` (it is a FastAPI transitive dep and is listed explicitly in the project's deps). No `uv add` required.

## Risks / Trade-offs

- **`AnyEvent` union is open-closed:** adding a ninth event variant later requires updating `AnyEvent` and re-generating the discriminated-union annotation. Low risk at this stage; the eight variants are fully specified in plan.md.
- **Redaction regex may miss novel auth patterns:** The regex covers known HTTP header patterns; bearer tokens embedded in JSON body content would not be caught. Acceptable for now; loop integration will be able to add more patterns if needed.
- **SQLite JSONL + `(run_id, seq)` UNIQUE constraint:** a race condition is possible if two threads write to the same `run_id` concurrently. Not a problem at this stage (single-threaded per request); noted for the async API ticket.
- **`:memory:` default in tests:** all tests use `path=":memory:"`, which matches `LocatorCache` convention. File-backed tests are not needed for the unit test surface.

## Open Questions

(none — all decisions resolved above)
