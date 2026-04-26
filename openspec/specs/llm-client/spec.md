# llm-client Specification

## Purpose
TBD - created by archiving change implement-llm-client. Update Purpose after archive.
## Requirements
### Requirement: OpenAI-compatible chat completions

The system SHALL provide a `chat(messages, ...)` interface that POSTs to `<base_url>/v1/chat/completions` using the OpenAI chat-completions request shape and returns a parsed response exposing `content`, `tool_calls`, `finish_reason`, `model`, `usage`, `usd`, and the raw response dict.

The `usd` field SHALL be a `float` computed by `compute_usd(usage.prompt_tokens, usage.completion_tokens, model, price_table)` using the price table injected into `LLMClient` at construction time or loaded lazily from `task2/config/pricing.toml`. No provider rate SHALL be hardcoded in the `LLMClient` implementation.

#### Scenario: Sends OpenAI-shaped request body

- **WHEN** a caller invokes `chat(messages=[{"role": "user", "content": "hi"}], model="qwen3.5", temperature=0.0)`
- **THEN** the system SHALL issue an HTTP POST to `<base_url>/v1/chat/completions`
- **AND** the request body SHALL be JSON containing `{"model": "qwen3.5", "messages": [{"role": "user", "content": "hi"}], "temperature": 0.0}`
- **AND** the request SHALL include `Content-Type: application/json`

#### Scenario: Forwards tools and seed when provided

- **WHEN** a caller invokes `chat(..., tools=[{"type": "function", "function": {"name": "x"}}], seed=7)`
- **THEN** the request body SHALL include `tools` exactly as provided
- **AND** the request body SHALL include `"seed": 7`

#### Scenario: Omits optional fields when not provided

- **WHEN** a caller invokes `chat(messages=..., model=...)` without `tools` or `seed`
- **THEN** the request body SHALL NOT include a `tools` key
- **AND** the request body SHALL NOT include a `seed` key

#### Scenario: Parses successful response and computes usd

- **WHEN** the API returns `{"id": "...", "model": "qwen3.5", "choices": [{"message": {"role": "assistant", "content": "hello"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 1000, "completion_tokens": 500, "total_tokens": 1500}}`
- **AND** the price table has `qwen3.5` rates `prompt_per_1k=0.002, completion_per_1k=0.006`
- **THEN** `ChatResponse.content` SHALL be `"hello"`
- **AND** `ChatResponse.usd` SHALL equal `1.0 * 0.002 + 0.5 * 0.006 == 0.005`
- **AND** `ChatResponse.usage.prompt_tokens` SHALL equal `1000`

#### Scenario: Parses tool-call response

- **WHEN** the API returns a choice whose `message.tool_calls` is `[{"id": "c1", "type": "function", "function": {"name": "click", "arguments": "{\"intent\": \"submit\"}"}}]`
- **THEN** `ChatResponse.tool_calls` SHALL contain one entry with `id="c1"`, `name="click"`, and `arguments="{\"intent\": \"submit\"}"` preserved as a string
- **AND** `ChatResponse.content` SHALL be `None` if the message has no text content

### Requirement: LLMClient accepts price_table constructor argument

`LLMClient.__init__` SHALL accept an optional `price_table: dict | None = None` argument. When provided, it SHALL be used for USD computation. When `None`, the client SHALL lazy-load from `task2/config/pricing.toml` on first use. Tests SHALL inject a synthetic price table dict to avoid file I/O.

#### Scenario: Injected price table is used without file I/O

- **WHEN** `LLMClient(base_url=..., model="m", price_table={"models": {}, "default": {"prompt_per_1k": 0.001, "completion_per_1k": 0.002}})` is constructed and `chat()` is called
- **THEN** `ChatResponse.usd` SHALL be computed from the injected table
- **AND** no file read of `pricing.toml` SHALL occur

### Requirement: Configuration via environment variables and explicit overrides

The system SHALL resolve `base_url`, `model`, and `api_key` in the order: explicit kwarg, then environment variable (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`), then default. The default for `base_url` SHALL be `http://localhost:8090`. There SHALL be no default for `model` or `api_key`.

#### Scenario: Default base URL when env unset

- **GIVEN** `LLM_BASE_URL` is unset
- **WHEN** `chat(..., model="m")` is invoked without an explicit `base_url`
- **THEN** the request SHALL be sent to `http://localhost:8090/v1/chat/completions`

#### Scenario: Environment variable honored

- **GIVEN** `LLM_BASE_URL=https://api.example.com/v1` and `LLM_MODEL=qwen3.5`
- **WHEN** `chat(messages=[...])` is invoked without explicit `base_url` or `model`
- **THEN** the request SHALL be sent to `https://api.example.com/v1/v1/chat/completions`
- **AND** the request body SHALL include `"model": "qwen3.5"`

#### Scenario: Explicit kwarg overrides environment

- **GIVEN** `LLM_BASE_URL=https://env.example.com`
- **WHEN** `chat(..., base_url="https://override.example.com", model="m")` is invoked
- **THEN** the request SHALL be sent to `https://override.example.com/v1/chat/completions`

#### Scenario: Missing model raises configuration error

- **GIVEN** `LLM_MODEL` is unset
- **WHEN** `chat(messages=[...])` is invoked without an explicit `model`
- **THEN** the system SHALL raise `LLMError` with `kind="config"`
- **AND** no HTTP request SHALL be issued

### Requirement: Authorization header policy

The system SHALL include an `Authorization: Bearer <key>` header when an API key is configured (kwarg or `LLM_API_KEY`), and SHALL omit the `Authorization` header entirely when no key is configured.

#### Scenario: API key sent as bearer token

- **GIVEN** `LLM_API_KEY=sk-test`
- **WHEN** `chat(..., model="m")` is invoked
- **THEN** the outgoing request SHALL include header `Authorization: Bearer sk-test`

#### Scenario: No authorization header when key absent

- **GIVEN** `LLM_API_KEY` is unset and no `api_key` kwarg is provided
- **WHEN** `chat(..., model="m")` is invoked
- **THEN** the outgoing request SHALL NOT include an `Authorization` header

### Requirement: Typed error model

The system SHALL surface failures as a single `LLMError` exception carrying `kind ∈ {"config", "transport", "http", "decode"}`, `status` (int or None), `body` (str truncated to 2048 bytes or None), and `cause` (original exception or None). Callers SHALL use `kind` to classify failures.

#### Scenario: HTTP non-2xx response

- **WHEN** the API returns HTTP 500 with body `"upstream timeout"`
- **THEN** the system SHALL raise `LLMError` with `kind="http"`, `status=500`, and `body="upstream timeout"`

#### Scenario: Network/transport failure

- **WHEN** the HTTP layer raises a connection error
- **THEN** the system SHALL raise `LLMError` with `kind="transport"`
- **AND** `cause` SHALL be the original exception

#### Scenario: Malformed response body

- **WHEN** the API returns HTTP 200 with body that is not valid JSON, or JSON missing `choices`
- **THEN** the system SHALL raise `LLMError` with `kind="decode"`

#### Scenario: Body truncation in error

- **WHEN** the API returns an error response whose body exceeds 2048 bytes
- **THEN** `LLMError.body` SHALL be truncated to at most 2048 bytes

### Requirement: Reusable client class

The system SHALL provide an `LLMClient` class whose constructor captures `base_url`, `model`, `api_key`, and `timeout`, and whose `chat(...)` method reuses the underlying HTTP connection across calls.

#### Scenario: Constructor-level configuration applies to subsequent calls

- **WHEN** a caller constructs `LLMClient(base_url="https://x.example.com", model="m")` and invokes `.chat(messages=[...])` twice
- **THEN** both requests SHALL be sent to `https://x.example.com/v1/chat/completions`
- **AND** both request bodies SHALL include `"model": "m"`

#### Scenario: Per-call kwargs override constructor configuration

- **WHEN** a caller constructs `LLMClient(model="default-m")` and invokes `.chat(messages=[...], model="other-m")`
- **THEN** the request body SHALL include `"model": "other-m"`

