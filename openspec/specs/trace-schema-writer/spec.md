# trace-schema-writer Specification

## Purpose
TBD - created by archiving change implement-trace-schema-writer. Update Purpose after archive.
## Requirements

### Requirement: Run model

The system SHALL provide `agent.trace.Run` — a Pydantic `BaseModel` representing a single task execution. It SHALL have the following fields:

- `run_id: str` — unique identifier (ULID or UUID4 string); set by the caller.
- `task: str` — verbatim NL task as given to the agent.
- `expect_schema: dict | None` — declared output schema, if provided; `None` otherwise.
- `budget: RunBudget` — typed submodel with fields `steps: int`, `usd: float`, `seconds: int`.
- `llm: RunLLM` — typed submodel with fields `base_url: str`, `model: str`, `temperature: float`, `seed: int | None`.
- `agent_version: str` — git SHA or other version string of the running code.
- `started_at: str` — ISO 8601 timestamp.
- `ended_at: str | None` — ISO 8601 timestamp; `None` until the run closes.
- `status: Literal["succeeded", "unverified", "failed", "blocked", "timeout"] | None` — `None` while in progress.
- `final: RunFinal | None` — typed submodel with fields `result: dict | None`, `evidence: dict | None`, `failure: dict | None`; `None` until closed.
- `totals: RunTotals | None` — typed submodel with fields `steps: int`, `llm_calls: int`, `prompt_tokens: int`, `completion_tokens: int`, `usd: float`, `browser_ms: int`; `None` until closed.

`budget`, `llm`, `final`, and `totals` SHALL be Pydantic `BaseModel` subclasses (`RunBudget`, `RunLLM`, `RunFinal`, `RunTotals`) so malformed shapes (missing keys, wrong value types) raise `pydantic.ValidationError` at write time rather than persisting silently.

`Run` SHALL be serializable to JSON via `model_dump_json()` and deserializable from JSON via `model_validate_json()` with round-trip equality.

#### Scenario: Run round-trips through JSON

- **WHEN** a `Run` instance is serialized via `run.model_dump_json()`
- **AND** the resulting JSON string is deserialized via `Run.model_validate_json(json_str)`
- **THEN** the deserialized instance SHALL equal the original instance

#### Scenario: Run accepts None for optional fields

- **WHEN** a `Run` is constructed with `expect_schema=None`, `ended_at=None`, `status=None`, `final=None`, `totals=None`
- **THEN** construction SHALL succeed
- **AND** each optional field SHALL serialize to `null` in JSON

### Requirement: EventBase shared fields

The system SHALL provide `agent.trace.EventBase` — a Pydantic `BaseModel` that all event variants inherit from. It SHALL define:

- `run_id: str` — links the event to its `Run`.
- `seq: int` — strictly increasing integer within a run; events are ordered by `seq`.
- `ts: str` — ISO 8601 timestamp of the event.
- `step_id: str | None` — logical step identifier within the run; `None` for events not associated with a specific step.
- `kind: str` — discriminator field; each subclass overrides this with a `Literal["..."]` value.

#### Scenario: EventBase fields are present on every event variant

- **WHEN** any event variant (e.g. `ObservationEvent`, `LLMCallEvent`) is constructed
- **THEN** the instance SHALL expose `run_id`, `seq`, `ts`, `step_id`, and `kind` attributes

### Requirement: ObservationEvent model

The system SHALL provide `agent.trace.ObservationEvent(EventBase)` with `kind: Literal["observation"]` and these additional fields:

- `url: str` — current page URL.
- `title: str` — current page title.
- `ax_tree_digest: str` — trimmed AX tree shown to the LLM (exact prompt input).
- `ax_fingerprint: str` — hash for drift detection.
- `screenshot_ref: str` — path or blob ID; not inlined.
- `viewport: dict` — keys `w: int`, `h: int`.
- `last_actions: list[dict]` — ordered list of actions dispatched since the previous observation. Each entry SHALL have keys `tool: str`, `intent: str`, `outcome: Literal["ok", "error"]`, and optionally `error: str` when `outcome == "error"`. Defaults to `[]` (empty list) when no actions were taken (e.g. first step).

#### Scenario: ObservationEvent round-trips through JSON

- **WHEN** an `ObservationEvent` is serialized and deserialized
- **THEN** the result SHALL equal the original

#### Scenario: ObservationEvent accepts last_actions list with entries

- **WHEN** an `ObservationEvent` is constructed with `last_actions=[{"tool": "goto", "intent": "{'url': 'http://x.com'}", "outcome": "ok"}]`
- **THEN** construction SHALL succeed
- **AND** `event.last_actions[0]["tool"]` SHALL equal `"goto"`
- **AND** the JSON round-trip SHALL preserve the `last_actions` list

#### Scenario: ObservationEvent defaults last_actions to empty list

- **WHEN** an `ObservationEvent` is constructed without supplying `last_actions`
- **THEN** `event.last_actions` SHALL equal `[]`
- **AND** the serialized JSON SHALL contain `"last_actions": []`

#### Scenario: ObservationEvent last_actions entry with error outcome round-trips

- **WHEN** an `ObservationEvent` is constructed with `last_actions=[{"tool": "read", "intent": "Submit button", "outcome": "error", "error": "Error: could not locate element"}]`
- **THEN** the JSON round-trip SHALL preserve the `"error"` key in the entry
- **AND** `event.last_actions[0]["outcome"]` SHALL equal `"error"`

### Requirement: PlanEvent model

The system SHALL provide `agent.trace.PlanEvent(EventBase)` with `kind: Literal["plan"]` and:

- `reason: Literal["initial", "replan"]`.
- `steps: list[str]` — ordered NL steps the planner produced.
- `llm_call_id: str` — references the `LLMCallEvent` for this planning call.

#### Scenario: PlanEvent round-trips through JSON

- **WHEN** a `PlanEvent` is serialized and deserialized
- **THEN** the result SHALL equal the original

### Requirement: DecisionEvent model

The system SHALL provide `agent.trace.DecisionEvent(EventBase)` with `kind: Literal["decision"]` and:

- `intent: str` — e.g. `"click the Submit button"`.
- `tool: Literal["goto","click","type","select","read","wait_for","back","screenshot","done","fail"]`.
- `args: dict` — tool arguments.
- `rationale: str` — LLM's stated reason (1–2 lines).
- `llm_call_id: str` — references the `LLMCallEvent`.

#### Scenario: DecisionEvent round-trips through JSON

- **WHEN** a `DecisionEvent` is serialized and deserialized
- **THEN** the result SHALL equal the original

### Requirement: LocateEvent model

The system SHALL provide `agent.trace.LocateEvent(EventBase)` with `kind: Literal["locate"]` and:

- `intent: str`.
- `tier: Literal["cache","L1_ax","L2_dom","L3_rerank","L4_vision"]`.
- `outcome: Literal["hit","miss","ambiguous","error"]`.
- `candidates: list[dict]` — each dict has keys `ax_role: str`, `ax_name: str`, `selector: str`, `score: float`; capped list.
- `chosen: dict | None` — keys `selector: str`, `ax_fingerprint: str`, `confidence: float`; `None` on miss/error.
- `cache_action: Literal["read","write","invalidate"] | None`.
- `ms: int` — elapsed milliseconds.

#### Scenario: LocateEvent round-trips through JSON with None chosen

- **WHEN** a `LocateEvent` with `outcome="miss"` and `chosen=None` is serialized and deserialized
- **THEN** the result SHALL equal the original with `chosen` remaining `None`

### Requirement: ActEvent model

The system SHALL provide `agent.trace.ActEvent(EventBase)` with `kind: Literal["act"]` and:

- `tool: str` — name of the browser tool executed.
- `args: dict` — arguments passed to the tool.
- `outcome: Literal["ok","no_effect","nav","timeout","error"]`.
- `diff: dict` — keys `url_changed: bool`, `ax_changed: bool`, `error: str | None`.
- `ms: int`.

#### Scenario: ActEvent round-trips through JSON

- **WHEN** an `ActEvent` is serialized and deserialized
- **THEN** the result SHALL equal the original

### Requirement: SupervisorEvent model

The system SHALL provide `agent.trace.SupervisorEvent(EventBase)` with `kind: Literal["supervisor"]` and:

- `trigger_event_seq: int` — `seq` of the Act or Locate event that triggered supervisor escalation.
- `classified_as: Literal["LocatorMiss","Ambiguous","NoEffect","FormError","NavDrift","Blocked","Timeout"]`.
- `policy: Literal["next_tier","rerank","sweep_overlay","replan","halt"]`.
- `attempt: int` — position in the strategy ladder (1..N).

#### Scenario: SupervisorEvent round-trips through JSON

- **WHEN** a `SupervisorEvent` is serialized and deserialized
- **THEN** the result SHALL equal the original

### Requirement: LLMCallEvent model

The system SHALL provide `agent.trace.LLMCallEvent(EventBase)` with `kind: Literal["llm_call"]` and:

- `llm_call_id: str` — referenced by `PlanEvent` and `DecisionEvent`.
- `purpose: Literal["plan","decide","locate_rerank","locate_vision","classify_failure","verify_evidence"]`.
- `model: str`.
- `base_url: str`.
- `prompt: dict` — keys `system: str | None`, `messages: list[dict]`, `tools: list[dict] | None`; full prompt for deterministic replay.
- `response: dict` — keys `content: str | None`, `tool_calls: list[dict] | None`, `finish_reason: str`.
- `tokens: dict` — keys `prompt: int`, `completion: int`.
- `usd: float`.
- `ms: int`.

#### Scenario: LLMCallEvent round-trips through JSON

- **WHEN** an `LLMCallEvent` is serialized and deserialized
- **THEN** the result SHALL equal the original

### Requirement: DoneEvent model

The system SHALL provide `agent.trace.DoneEvent(EventBase)` with `kind: Literal["done"]` and:

- `result: dict` — structured output from the agent.
- `evidence: dict` — keys `url: str`, `text_snippet: str`, `screenshot_ref: str | None`, `ax_path: str | None`.
- `verifier: dict` — keys `ok: bool`, `reasons: list[str]`.

#### Scenario: DoneEvent round-trips through JSON

- **WHEN** a `DoneEvent` is serialized and deserialized
- **THEN** the result SHALL equal the original

### Requirement: AnyEvent discriminated union

The system SHALL provide `agent.trace.AnyEvent` — a type alias for the discriminated union of all eight event variants, discriminated on the `kind` field. It SHALL be usable with `TypeAdapter(AnyEvent).validate_json(line)` to deserialize any event line from a JSONL stream into the correct concrete subtype.

#### Scenario: AnyEvent deserializes each variant by kind

- **WHEN** a JSON string with `"kind": "observation"` is deserialized via `TypeAdapter(AnyEvent).validate_json(json_str)`
- **THEN** the result SHALL be an instance of `ObservationEvent`
- **WHEN** a JSON string with `"kind": "llm_call"` is deserialized
- **THEN** the result SHALL be an instance of `LLMCallEvent`
- **WHEN** a JSON string with `"kind": "done"` is deserialized
- **THEN** the result SHALL be an instance of `DoneEvent`

### Requirement: TraceWriter append-only API

The system SHALL provide `agent.trace.TraceWriter` — a class that persists `Run` and `AnyEvent` objects to SQLite. Constructor: `TraceWriter(path: str = ":memory:")`. It SHALL:

- Open a SQLite connection to `path` and call `_ensure_schema()` which creates `traces.runs` and `traces.events` tables if they do not exist.
- `open_run(run: Run) -> None` — INSERT the run as a JSON blob into `traces.runs`. Raise `sqlite3.IntegrityError` if the `run_id` already exists. Raise `ValueError` if `run.status` is non-`None` (a run with terminal status cannot be opened — the writer would otherwise accept appended events whose timeline contradicts the closed state).
- `append_event(event: AnyEvent) -> None` — verify the run exists and is still open, validate `event.seq > last_seq_for_run`, then INSERT the event's JSON into `traces.events`. Raise `LookupError` if `event.run_id` has no row in `traces.runs` OR if the run is already closed (`status` is non-NULL). Raise `SeqError` if the seq is not strictly greater than the last appended seq for this run.
- `close_run(run_id: str, *, status: str, ended_at: str, final: dict, totals: dict) -> None` — UPDATE the `traces.runs` row to set `status`, `ended_at`, `final_json`, `totals_json`, AND rewrite the `payload` JSON blob so the canonical `Run` reflects the closed state. The merged values SHALL be re-validated against the `Run` schema before the row is written, so an invalid `status` (or any other field) raises `pydantic.ValidationError` and leaves the existing payload untouched. The helper columns `final_json` and `totals_json` SHALL be serialized from the validated `Run` (not from the raw inputs) so coercible inputs cannot diverge from `payload`. Raise `LookupError` if `run_id` has no row. Raise `ValueError` if the run is already closed (`status` is non-`None` in the existing payload).
- `close() -> None` — close the SQLite connection.
- `__enter__` / `__exit__` context manager: call `close()` on exit.

The `traces.runs` table SHALL have columns: `run_id TEXT PRIMARY KEY NOT NULL`, `payload TEXT NOT NULL` (full `Run` JSON).

The `traces.events` table SHALL have columns: `run_id TEXT NOT NULL`, `seq INTEGER NOT NULL`, `payload TEXT NOT NULL`, with a `UNIQUE(run_id, seq)` constraint.

#### Scenario: TraceWriter open_run and append_event persist data

- **GIVEN** a `TraceWriter` opened with `:memory:`
- **WHEN** `open_run(run)` is called with a valid `Run`
- **AND** `append_event(event)` is called with `event.seq = 1`
- **THEN** querying `traces.runs` for `run.run_id` SHALL return one row
- **AND** querying `traces.events` for `run.run_id` SHALL return one row with `seq = 1`

#### Scenario: TraceWriter rejects duplicate seq

- **GIVEN** a `TraceWriter` with one event at `seq=1` appended
- **WHEN** `append_event(event)` is called again with `seq=1`
- **THEN** a `SeqError` SHALL be raised

#### Scenario: TraceWriter rejects out-of-order seq

- **GIVEN** a `TraceWriter` with one event at `seq=5` appended
- **WHEN** `append_event(event)` is called with `seq=3`
- **THEN** a `SeqError` SHALL be raised

#### Scenario: TraceWriter accepts strictly increasing seq

- **GIVEN** a `TraceWriter` with events at seq=1, seq=2
- **WHEN** `append_event(event)` is called with `seq=3`
- **THEN** the event SHALL be persisted without error

### Requirement: SeqError exception

The system SHALL provide `agent.trace.SeqError` — a `ValueError` subclass raised by `TraceWriter.append_event()` when `event.seq` is not strictly greater than the last appended seq for that run. It SHALL carry the `expected_min` (int) and `got` (int) values for diagnostics.

#### Scenario: SeqError carries expected_min and got

- **WHEN** `SeqError(expected_min=3, got=2)` is raised and caught
- **THEN** `err.expected_min` SHALL equal `3`
- **AND** `err.got` SHALL equal `2`

### Requirement: redact helper

The system SHALL provide `agent.trace.redact(event: AnyEvent) -> AnyEvent` — a function that returns a new event instance with secret-typed fields replaced by the string `"[REDACTED]"`. Secret fields are:

- For `LLMCallEvent`: any message in `prompt.messages` whose `content` string matches the pattern `(?i)(set-cookie|cookie|authorization):\s*\S+` SHALL have the matching substring(s) replaced with `[REDACTED]`. Entries that are not dicts (or that lack a string `content`) SHALL be passed through unchanged rather than crashing redaction.
- For `DecisionEvent` or `ActEvent` with `tool == "type"`: `args["text"]` SHALL be replaced with `"[REDACTED]"`. Both event variants are covered because `DecisionEvent` records the LLM's intent and `ActEvent` records the executed action — leaking either persists the typed text.
- For all other event variants: the event SHALL be returned unchanged.

`redact()` SHALL NOT mutate the original event; it SHALL return a new model instance.

`TraceWriter.append_event()` SHALL call `redact()` before serializing the event to JSON.

#### Scenario: redact strips Authorization header from LLMCallEvent prompt messages

- **GIVEN** an `LLMCallEvent` where `prompt.messages` contains `{"role": "user", "content": "Authorization: Bearer secret-token"}`
- **WHEN** `redact(event)` is called
- **THEN** the returned event's `prompt.messages` content SHALL contain `"[REDACTED]"` in place of the bearer token substring
- **AND** the original event SHALL be unchanged

#### Scenario: redact replaces typed text in DecisionEvent for type tool

- **GIVEN** a `DecisionEvent` with `tool="type"` and `args={"intent": "password field", "text": "MyP@ssw0rd"}`
- **WHEN** `redact(event)` is called
- **THEN** the returned event's `args["text"]` SHALL equal `"[REDACTED]"`
- **AND** the original event's `args["text"]` SHALL equal `"MyP@ssw0rd"`

#### Scenario: redact leaves non-secret events unchanged

- **GIVEN** an `ObservationEvent`
- **WHEN** `redact(event)` is called
- **THEN** the returned event SHALL equal the original event

#### Scenario: TraceWriter calls redact before persisting LLMCallEvent

- **GIVEN** a `TraceWriter` opened with `:memory:`
- **AND** an `LLMCallEvent` whose `prompt.messages` contains `"Authorization: Bearer secret"`
- **WHEN** `append_event(event)` is called
- **THEN** the stored JSON payload in `traces.events` SHALL NOT contain the literal string `"secret"`
- **AND** the stored JSON SHALL contain `"[REDACTED]"`

#### Scenario: redact masks typed text on ActEvent

- **GIVEN** an `ActEvent` with `tool="type"` and `args={"intent": "password field", "text": "MyP@ssw0rd"}`
- **WHEN** `redact(event)` is called
- **THEN** the returned event's `args["text"]` SHALL equal `"[REDACTED]"`
- **AND** the original event's `args["text"]` SHALL equal `"MyP@ssw0rd"`

#### Scenario: append_event rejects unknown run_id

- **GIVEN** a `TraceWriter` with no run opened
- **WHEN** `append_event(event)` is called with a `run_id` that has no row in `traces.runs`
- **THEN** a `LookupError` SHALL be raised

#### Scenario: append_event rejects events after close_run

- **GIVEN** a `TraceWriter` with a run opened and then closed via `close_run(...)`
- **WHEN** `append_event(event)` is called for that `run_id`
- **THEN** a `LookupError` SHALL be raised

#### Scenario: close_run rejects double-close

- **GIVEN** a `TraceWriter` with a run opened and then closed via `close_run(...)`
- **WHEN** `close_run(...)` is called again for the same `run_id`
- **THEN** a `ValueError` SHALL be raised
- **AND** the `traces.runs` row for that `run_id` SHALL retain the original closing values

#### Scenario: close_run normalizes helper columns from validated Run

- **GIVEN** a `TraceWriter` with a run opened
- **WHEN** `close_run` is called with a `totals` dict whose values are coercible into the `RunTotals` types (e.g. `"3"` for `steps: int`)
- **THEN** the `totals_json` column SHALL contain the validated, normalized values (e.g. `3`)
- **AND** the `totals_json` column SHALL parse to the same dict as `payload["totals"]`

#### Scenario: open_run rejects a Run with terminal status

- **GIVEN** a `TraceWriter`
- **WHEN** `open_run(run)` is called with `run.status` set to a terminal value (e.g. `"succeeded"`)
- **THEN** a `ValueError` SHALL be raised
- **AND** the `traces.runs` table SHALL NOT contain a row for that `run_id`

#### Scenario: redact tolerates non-dict prompt messages

- **GIVEN** an `LLMCallEvent` whose `prompt.messages` contains a non-dict entry (e.g. a bare string)
- **WHEN** `redact(event)` is called
- **THEN** redaction SHALL NOT raise
- **AND** the non-dict entry SHALL be returned unchanged in the new event

#### Scenario: close_run rejects invalid Run state

- **GIVEN** a `TraceWriter` with a run opened
- **WHEN** `close_run` is called with `status="success"` (not in the `Run.status` Literal)
- **THEN** `pydantic.ValidationError` SHALL be raised
- **AND** the existing `payload` row in `traces.runs` SHALL be unchanged

#### Scenario: close_run rewrites the payload blob

- **GIVEN** a `TraceWriter` with a run opened via `open_run(run)` where `status`, `final`, and `totals` are `None`
- **WHEN** `close_run(run_id, status="succeeded", ended_at=..., final={...}, totals={...})` is called
- **THEN** the `payload` JSON in `traces.runs` for that `run_id` SHALL parse back to a `Run` whose `status`, `ended_at`, `final`, and `totals` reflect the closing values
