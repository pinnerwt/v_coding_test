## Why

The agent loop (ticket #12) produces no structured audit trail: there is no way to replay, debug, or regression-test a run after the fact. This change introduces the `trace.py` module — the append-only writer that persists a `Run` header and each `Event` variant to SQLite JSONL — making every run inspectable and replayable without re-running the live browser.

## What Changes

- New module `task2/agent/trace.py`: Pydantic models for `Run` and all eight `Event` variants (`ObservationEvent`, `PlanEvent`, `DecisionEvent`, `LocateEvent`, `ActEvent`, `SupervisorEvent`, `LLMCallEvent`, `DoneEvent`). Shared event fields: `run_id`, `seq`, `ts`, `step_id`, plus `kind` discriminator.
- `TraceWriter` class: append-only API backed by SQLite (`traces.runs` + `traces.events`). Enforces strictly increasing `seq` on every `append_event()` call; raises `SeqError` on violation.
- Redaction: secret-typed fields (cookies, auth tokens, user-typed secrets per plan.md "What we deliberately do NOT store") are redacted before write. A `redact()` helper strips them from `LLMCallEvent.prompt.messages` and `DecisionEvent.args`.
- New test file `task2/tests/agent/test_trace.py`: JSON round-trip for every model, seq-ordering enforcement, and redaction verification.
- No integration with `loop.py` or any other module yet — the writer is the standalone unit under test in this ticket.

## Capabilities

### New Capabilities

- `trace-schema-writer`: Pydantic models for `Run` + all `Event` variants, SQLite-backed append-only `TraceWriter`, strictly-increasing `seq` enforcement, and secret-field redaction before write.

### Modified Capabilities

(none — no existing spec-level requirements change)

## Impact

- **Code**: `task2/agent/trace.py` (new); `task2/tests/agent/test_trace.py` (new).
- **Dependencies**: `pydantic` (already used in the project via FastAPI path; confirm with `uv add pydantic` if not already listed), `python-ulid` or similar for ULID generation (or use `uuid` with a ULID-shaped string for now — decided in design.md).
- **Existing modules**: `loop.py`, `locate.py`, `supervisor.py`, `browser.py`, `llm.py`, `locator_cache.py` are all unchanged by this ticket.
- **SQLite schema**: two new tables — `traces.runs` (one row per `Run`) and `traces.events` (one JSONL row per event). Single SQLite file shared with the locator cache or a dedicated trace DB — decided in design.md.
