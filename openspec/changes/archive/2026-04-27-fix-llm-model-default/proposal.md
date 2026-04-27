## Why

`scripts/eval.py::build_clients()` defaults `LLM_MODEL` to `"qwen3"`, while `api/server.py` defaults to `"qwen3-5-27b"` — the actual model name served at `http://localhost:8090`. This mismatch causes every eval-runner invocation against the live Qwen instance to 404 on the first LLM call unless `LLM_MODEL` is set explicitly, which has silently blocked live smoke-testing since ticket #32.

## What Changes

- Add `_DEFAULT_LLM_MODEL = "qwen3-5-27b"` constant to `task2/agent/llm.py` (single source of truth alongside the existing `_DEFAULT_BASE_URL`).
- Remove the local `_DEFAULT_LLM_MODEL = "qwen3-5-27b"` in `task2/api/server.py` (line 22) and import/reference the one from `agent/llm.py`.
- Change `scripts/eval.py::build_clients()` to fall back to `agent.llm._DEFAULT_LLM_MODEL` instead of the hard-coded string `"qwen3"`.
- Update `scripts/benchmark.py` if it also consumes `build_clients()` (it delegates fully, so it picks up the fix automatically, but must be verified).
- Add a unit test asserting both call sites resolve the same default model string when `LLM_MODEL` is unset.

## Capabilities

### New Capabilities
- `llm-model-default`: Shared `_DEFAULT_LLM_MODEL` constant in `agent/llm.py` consumed by both `api/server.py` and `scripts/eval.py`, with a unit test verifying alignment.

### Modified Capabilities
- `eval-runner`: The `build_clients()` function REQUIREMENT changes — it must resolve the LLM model default from the shared constant, not from a local hard-coded string.
- `llm-client`: The `_DEFAULT_LLM_MODEL` constant is now exported from `agent/llm.py`; the env-var resolution requirement is unchanged but the "no model default" clause is relaxed — a module-level default now exists.

## Impact

- `task2/agent/llm.py` — add `_DEFAULT_LLM_MODEL = "qwen3-5-27b"` (no other behaviour changes).
- `task2/api/server.py` — remove its own `_DEFAULT_LLM_MODEL`, import from `agent.llm`.
- `task2/scripts/eval.py` — update `build_clients()` to reference `agent.llm._DEFAULT_LLM_MODEL`.
- `task2/tests/` — new unit test `test_llm_model_default.py`.
- No API surface changes; no new dependencies; no migration needed.
