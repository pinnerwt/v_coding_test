## ADDED Requirements

### Requirement: _DEFAULT_LLM_MODEL module constant
`agent/llm.py` SHALL define a module-level string constant `_DEFAULT_LLM_MODEL = "qwen3-5-27b"` alongside the existing `_DEFAULT_BASE_URL`. This constant is the authoritative fallback model name for the Task 2 stack; it is consumed by callers (`api/server.py`, `scripts/eval.py`) — not by `LLMClient` internally.

#### Scenario: _DEFAULT_LLM_MODEL is importable from agent.llm
- **WHEN** `from agent.llm import _DEFAULT_LLM_MODEL` is executed in a test or production module
- **THEN** the import SHALL succeed and the value SHALL equal `"qwen3-5-27b"`

## MODIFIED Requirements

### Requirement: Configuration via environment variables and explicit overrides

The system SHALL resolve `base_url`, `model`, and `api_key` in the order: explicit kwarg, then environment variable (`LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`), then default. The default for `base_url` SHALL be `http://localhost:8090`. There SHALL be no default for `model` or `api_key` inside `LLMClient` itself — callers that need a fallback SHALL pass `_DEFAULT_LLM_MODEL` explicitly.

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
