## ADDED Requirements

### Requirement: POST /tasks accepts and enqueues a task
The system SHALL accept a JSON body `{ "task": string, "expect_schema"?: object, "budget"?: { "steps"?: int, "usd"?: float, "seconds"?: int } }` at `POST /tasks`, validate that `task` is a non-empty string, create a `Run` record in SQLite with `status=null` (in-progress), enqueue the agent loop as a background task, and return HTTP 200 with body `{ "id": "<ulid>" }` before the agent has finished running.

#### Scenario: Valid task body returns run ID immediately
- **WHEN** a client sends `POST /tasks` with body `{ "task": "find the price of milk" }`
- **THEN** the server responds HTTP 200 with `{ "id": "<ulid>" }` within 200ms (before the agent completes)

#### Scenario: Missing task field returns 422
- **WHEN** a client sends `POST /tasks` with body `{}` (no `task` field)
- **THEN** the server responds HTTP 422 Unprocessable Entity

#### Scenario: Empty task string returns 422
- **WHEN** a client sends `POST /tasks` with body `{ "task": "" }`
- **THEN** the server responds HTTP 422 Unprocessable Entity

#### Scenario: Run is persisted before response
- **WHEN** `POST /tasks` is called with a valid body
- **THEN** a row exists in `traces_runs` with the returned `id` and `status IS NULL` before the background task completes

### Requirement: GET /tasks/{id} returns run state
The system SHALL return the current state of a run at `GET /tasks/{id}`. While the background task is executing, the response SHALL be `{ "status": "running" }`. Once the run completes, the response SHALL include `status`, `result`, `evidence`, and `totals` from the `Run` record. If the `id` does not exist, the system SHALL return HTTP 404.

#### Scenario: Running task returns status running
- **WHEN** a client calls `GET /tasks/{id}` while the agent background task is still executing
- **THEN** the server responds HTTP 200 with `{ "status": "running" }`

#### Scenario: Completed task returns final state
- **WHEN** a client calls `GET /tasks/{id}` after the agent background task has completed
- **THEN** the server responds HTTP 200 with a JSON object containing `"status"` (one of `succeeded`, `unverified`, `failed`, `blocked`, `timeout`), `"result"`, `"evidence"`, and `"totals"`

#### Scenario: Unknown task ID returns 404
- **WHEN** a client calls `GET /tasks/nonexistent-id`
- **THEN** the server responds HTTP 404

### Requirement: GET /tasks/{id}/trace streams JSONL events
The system SHALL return all trace events for a run at `GET /tasks/{id}/trace` as newline-delimited JSON (`Content-Type: application/x-ndjson`). Events SHALL be ordered by ascending `seq`. Each line SHALL be a valid JSON object matching one of the `AnyEvent` variants from `agent.trace`. If the `id` does not exist, the system SHALL return HTTP 404.

#### Scenario: Trace stream contains ordered events
- **WHEN** a client calls `GET /tasks/{id}/trace` for a completed run with N events
- **THEN** the response body contains N newline-terminated JSON lines, ordered by `seq` ascending

#### Scenario: Content-Type is application/x-ndjson
- **WHEN** a client calls `GET /tasks/{id}/trace`
- **THEN** the `Content-Type` response header is `application/x-ndjson`

#### Scenario: Unknown trace ID returns 404
- **WHEN** a client calls `GET /tasks/nonexistent-id/trace`
- **THEN** the server responds HTTP 404

#### Scenario: Empty trace returns empty body
- **WHEN** a run exists but has no events (background task not yet started)
- **THEN** the response is HTTP 200 with an empty body (zero lines)

### Requirement: GET / serves task submission HTML page
The system SHALL serve a minimal HTML page at `GET /` that includes a form to submit a task (POSTs to `/tasks`) and a polling section that displays the run result once the task completes. The page SHALL NOT require any external CSS or JavaScript dependencies (all inline).

#### Scenario: Root route returns HTML
- **WHEN** a client sends `GET /`
- **THEN** the server responds HTTP 200 with `Content-Type: text/html` and a non-empty body

#### Scenario: HTML contains task form
- **WHEN** a client loads `GET /`
- **THEN** the response body contains a `<form>` element and an `<input>` or `<textarea>` for the task string

### Requirement: DB_PATH env var controls SQLite location
The system SHALL read the `DB_PATH` environment variable to determine the SQLite file path for all persistence operations (run records and trace events). When `DB_PATH` is not set, the system SHALL default to `./agent_tasks.db`. Both the write path (TraceWriter) and the read path (GET endpoints) SHALL use the same resolved path.

#### Scenario: Custom DB_PATH is respected
- **WHEN** the server starts with `DB_PATH=/tmp/test.db`
- **THEN** all SQLite reads and writes go to `/tmp/test.db`

#### Scenario: Default DB path used when env var absent
- **WHEN** the server starts without `DB_PATH` set
- **THEN** SQLite operations target `./agent_tasks.db`

### Requirement: LLM configuration read from environment
The system SHALL construct the `LLMClient` for each run using `LLM_BASE_URL` (default `http://localhost:8090`), `LLM_MODEL` (default `qwen3-5-27b`), and optional `LLM_API_KEY`. No hosted provider URL SHALL be hardcoded in the server source.

#### Scenario: LLM_BASE_URL is forwarded to LLMClient
- **WHEN** the server starts with `LLM_BASE_URL=http://custom-host:9999`
- **THEN** the `LLMClient` instance used for the run has `base_url="http://custom-host:9999"`

#### Scenario: Missing LLM_BASE_URL falls back to default
- **WHEN** `LLM_BASE_URL` is not set
- **THEN** the `LLMClient` uses `base_url="http://localhost:8090"`
