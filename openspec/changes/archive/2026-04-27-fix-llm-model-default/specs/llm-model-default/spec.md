## ADDED Requirements

### Requirement: Shared default LLM model constant
`task2/agent/llm.py` SHALL export a module-level string constant `_DEFAULT_LLM_MODEL = "qwen3-5-27b"`. This constant SHALL be the single authoritative source for the fallback model name used when the `LLM_MODEL` environment variable is unset.

No other file in the `task2/` tree SHALL define its own fallback LLM model string — any module that needs the default SHALL import `_DEFAULT_LLM_MODEL` from `agent.llm`.

#### Scenario: Constant exists in agent.llm with correct value
- **WHEN** `from agent.llm import _DEFAULT_LLM_MODEL` is executed
- **THEN** `_DEFAULT_LLM_MODEL` SHALL equal `"qwen3-5-27b"`

#### Scenario: api/server.py imports rather than redefines the constant
- **WHEN** `task2/api/server.py` is inspected
- **THEN** it SHALL NOT define its own `_DEFAULT_LLM_MODEL` assignment
- **AND** it SHALL reference `agent.llm._DEFAULT_LLM_MODEL` (via import or attribute access) for its LLM model fallback

#### Scenario: scripts/eval.py uses the shared constant for its build_clients fallback
- **WHEN** `task2/scripts/eval.py::build_clients()` is invoked without `LLM_MODEL` set in the environment
- **THEN** the `LLMClient` SHALL be constructed with `model` equal to `agent.llm._DEFAULT_LLM_MODEL`

### Requirement: Both call sites resolve the same default model
When `LLM_MODEL` is not set in the environment, both `api/server.py` and `scripts/eval.py::build_clients()` SHALL resolve the LLM model to `_DEFAULT_LLM_MODEL`. A unit test SHALL assert this property without requiring a live LLM connection.

#### Scenario: Unit test asserts same default across call sites
- **GIVEN** `LLM_MODEL` is not set in the process environment
- **WHEN** `build_clients()` from `scripts/eval.py` is called (with network patched so no HTTP call fires)
- **AND** the model that `api/server.py::_build_run()` would resolve is inspected (by reading `os.environ.get("LLM_MODEL", agent.llm._DEFAULT_LLM_MODEL)`)
- **THEN** both resolved model strings SHALL equal `"qwen3-5-27b"`
- **AND** `_DEFAULT_LLM_MODEL` from `agent.llm` SHALL equal `"qwen3-5-27b"`
