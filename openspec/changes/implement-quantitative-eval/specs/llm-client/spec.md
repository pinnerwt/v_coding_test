## MODIFIED Requirements

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
