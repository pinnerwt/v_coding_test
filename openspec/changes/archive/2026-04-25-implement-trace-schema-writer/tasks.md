## 1. Red — Failing Tests

- [x] 1.1 Create `task2/tests/agent/test_trace.py`. Add `test_run_round_trip`: construct a `Run` with all fields populated, serialize via `model_dump_json()`, deserialize via `Run.model_validate_json()`, assert equality.
- [x] 1.2 Add `test_run_optional_fields_null`: construct a `Run` with `expect_schema=None`, `ended_at=None`, `status=None`, `final=None`, `totals=None`; assert construction succeeds and serializes optional fields to `null`.
- [x] 1.3 Add one round-trip test per event variant: `test_observation_event_round_trip`, `test_plan_event_round_trip`, `test_decision_event_round_trip`, `test_locate_event_round_trip`, `test_act_event_round_trip`, `test_supervisor_event_round_trip`, `test_llm_call_event_round_trip`, `test_done_event_round_trip`.
- [x] 1.4 Add `test_locate_event_none_chosen`: `LocateEvent` with `outcome="miss"` and `chosen=None` round-trips with `chosen` remaining `None`.
- [x] 1.5 Add `test_any_event_discriminator`: serialize an `ObservationEvent`, `LLMCallEvent`, and `DoneEvent` to JSON strings, then deserialize each via `TypeAdapter(AnyEvent).validate_json(...)` and assert the returned types are the correct concrete subtypes.
- [x] 1.6 Add `test_seq_error_fields`: construct `SeqError(expected_min=3, got=2)`, assert `.expected_min == 3` and `.got == 2`.
- [x] 1.7 Add `test_trace_writer_basic_persist`: open a `TraceWriter(":memory:")`, call `open_run(run)` + `append_event(event, seq=1)`, query both tables directly via `writer._conn`, assert one row in each.
- [x] 1.8 Add `test_trace_writer_rejects_duplicate_seq`: append `seq=1`, then append `seq=1` again; assert `SeqError` is raised.
- [x] 1.9 Add `test_trace_writer_rejects_out_of_order_seq`: append `seq=5`, then append `seq=3`; assert `SeqError` is raised.
- [x] 1.10 Add `test_trace_writer_accepts_increasing_seq`: append `seq=1`, `seq=2`, `seq=3`; assert no error and `traces.events` has three rows.
- [x] 1.11 Add `test_redact_authorization_header`: construct an `LLMCallEvent` with a message whose content contains `"Authorization: Bearer secret-token"`; call `redact(event)`; assert the returned event's message content contains `"[REDACTED]"` and not `"secret-token"`; assert the original event is unchanged.
- [x] 1.12 Add `test_redact_type_tool_text`: construct a `DecisionEvent` with `tool="type"` and `args={"intent": "password field", "text": "MyP@ssw0rd"}`; call `redact(event)`; assert returned `args["text"] == "[REDACTED]"` and original `args["text"] == "MyP@ssw0rd"`.
- [x] 1.13 Add `test_redact_noop_for_observation`: construct an `ObservationEvent`; call `redact(event)`; assert returned event equals original.
- [x] 1.14 Add `test_trace_writer_redacts_before_persist`: open a `TraceWriter(":memory:")`; create an `LLMCallEvent` with `"Authorization: Bearer secret"` in a message; call `append_event()`; query `traces.events`, load the stored payload JSON, and assert `"secret"` does not appear in the payload but `"[REDACTED]"` does.
- [x] 1.15 Run `uv run pytest task2/tests/agent/test_trace.py -x` from `task2/` and confirm all tests fail with `ModuleNotFoundError` or `ImportError` (the module does not exist yet).

## 2. Green — Implement `agent/trace.py`

- [x] 2.1 Create `task2/agent/trace.py` with `from __future__ import annotations` and necessary imports (`pydantic`, `sqlite3`, `re`, `typing`).
- [x] 2.2 Implement `EventBase(BaseModel)` with fields `run_id: str`, `seq: int`, `ts: str`, `step_id: str | None`, `kind: str`.
- [x] 2.3 Implement all eight event variant models inheriting from `EventBase`, each setting `kind: Literal["<variant>"]` as a class-level field. Fields per variant as specified in `specs/trace-schema-writer/spec.md`.
- [x] 2.4 Implement `Run(BaseModel)` with all fields from the spec.
- [x] 2.5 Define `AnyEvent` as `Annotated[Union[ObservationEvent, PlanEvent, DecisionEvent, LocateEvent, ActEvent, SupervisorEvent, LLMCallEvent, DoneEvent], Field(discriminator="kind")]`. Create `_any_event_adapter = TypeAdapter(AnyEvent)` at module level for reuse.
- [x] 2.6 Implement `SeqError(ValueError)` with `__init__(self, *, expected_min: int, got: int)` storing both as instance attributes.
- [x] 2.7 Implement `redact(event: AnyEvent) -> AnyEvent`: for `LLMCallEvent`, scan each message's `content` string for `(?i)(set-cookie|cookie|authorization):\s*\S+` and replace matches with `[REDACTED]` using `re.sub`; return a new `LLMCallEvent` via `event.model_copy(update={"prompt": {**event.prompt, "messages": new_messages}})`. For `DecisionEvent` with `tool == "type"`, return `event.model_copy(update={"args": {**event.args, "text": "[REDACTED]"}})`. For all others return `event` unchanged.
- [x] 2.8 Implement `TraceWriter`: `__init__(path=":memory:")` opens SQLite and calls `_ensure_schema()`. `_ensure_schema()` creates `traces.runs` and `traces.events` tables with the columns and constraints from the spec.
- [x] 2.9 Implement `TraceWriter.open_run(run: Run) -> None`: INSERT `run_id` and `run.model_dump_json()` into `traces.runs`.
- [x] 2.10 Implement `TraceWriter.append_event(event: AnyEvent) -> None`: fetch `max(seq)` from `traces.events` for `event.run_id`; if `event.seq <= max_seq` (or `max_seq` is not None and `event.seq <= max_seq`), raise `SeqError(expected_min=max_seq + 1, got=event.seq)`; call `redact(event)`, serialize via `model_dump_json()`, INSERT into `traces.events`.
- [x] 2.11 Implement `TraceWriter.close_run(run_id, *, status, ended_at, final, totals) -> None`: UPDATE `traces.runs` setting additional columns. (Simplest approach: store updated fields as separate columns `status TEXT`, `ended_at TEXT`, `final_json TEXT`, `totals_json TEXT`; update them in `close_run`.)
- [x] 2.12 Implement `TraceWriter.close() -> None` and `__enter__` / `__exit__`.
- [x] 2.13 Run `uv run pytest task2/tests/agent/test_trace.py -x` from `task2/` and confirm all tests pass.

## 3. Full Test Suite

- [x] 3.1 Run `uv run pytest task2/tests/` from `task2/` and confirm all existing tests (loop, locate, supervisor, locator_cache, browser, llm) still pass — no regressions.

## 4. Lint and Format

- [x] 4.1 Run `uv run ruff check --fix .` from `task2/` to auto-fix any lint errors.
- [x] 4.2 Run `uv run ruff format .` from `task2/` to auto-format changed files.
- [x] 4.3 Run `uv run ruff check .` from `task2/` and confirm it exits clean (zero errors, zero warnings).

## 5. Refactor Under Green (if needed)

- [x] 5.1 Review `redact()` for correctness: ensure `model_copy(deep=True)` is used when mutating nested dicts so Pydantic does not share references between original and copy. Refactor only if tests remain green.
- [x] 5.2 Review `TraceWriter._ensure_schema()` for parity with `LocatorCache._ensure_schema()` pattern: use `PRAGMA table_info` to check existing columns before dropping and recreating. Refactor if the simpler `CREATE TABLE IF NOT EXISTS` is sufficient given tests pass.
- [x] 5.3 Verify that `TraceWriter` used as a context manager (`with TraceWriter() as w:`) calls `close()` on both normal exit and exception, and that the connection is `None` afterwards. Add a test if not already covered.
